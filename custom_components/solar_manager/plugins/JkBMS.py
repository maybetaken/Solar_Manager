"""JkBms device class for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import json
import logging
from typing import Any

from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)

from homeassistant.core import HomeAssistant

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)


class JkBms(BaseDevice):
    """JkBms device class for Solar Manager integration."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Init."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.slave_id = 15
        self.setup_protocol()
        self._register_to_name = {}
        self._unknown_registers = set()

    async def send_config(self) -> None:
        """Send config via MQTT."""
        try:
            config = {"segments": self.parser.protocol_data.get("segments", [])}
            await self.mqtt_manager.publish(
                self._build_topic("config"), json.dumps(config)
            )
        except Exception as e:
            _LOGGER.error("Config send failed: %s", e)

    def setup_protocol(self) -> None:
        """Setup protocol."""
        self.parser.register_callback(self.handle_cmd)

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device info based on JSON definition."""
        self._register_to_name = {}
        device_info = super().unpack_device_info()

        for register, details in self.parser.protocol_data.get("registers", {}).items():
            name = details.get("name")
            if not name:
                continue

            self._register_to_name[register] = name
            sensor_type = details.get("sensor_type", "sensor")

            # ★★★ 修复点：display_precision 默认值改为 None，不要用 0 ★★★
            # 只有当它是 None 时，HA 才允许字符串类型的状态
            entity_def = {
                "addressing": "byte",
                "name": name,
                "scale": details.get("scale", 1.0),
                "unit": details.get("unit"),
                "icon": details.get("icon"),
                "display_precision": details.get("display_precision"),
                "device": self,
                "offset": details.get("offset", 0),
                "device_class": details.get("device_class", "None"),
                "state_class": details.get("state_class", "None"),
            }

            if sensor_type == "sensor":
                if "enum" in details:
                    entity_def["enum_mapping"] = {
                        int(k, 16) if k.startswith("0x") else int(k): v
                        for k, v in details["enum"].items()
                    }
                device_info["sensor"].append(entity_def)

            elif sensor_type == "number":
                entity_def.update(
                    {
                        "min_value": details.get("min_value", -500000000),
                        "max_value": details.get("max_value", 500000000),
                        "step": details.get("step", 1.0),
                        "register": register,
                    }
                )
                device_info["number"].append(entity_def)

            elif sensor_type == "switch":
                entity_def.update(
                    {
                        "register": register,
                        "write_command": details.get("write_command", 10),
                    }
                )
                device_info["switch"].append(entity_def)

        return device_info

    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle incoming data."""
        parsed_data = self.parser.parse_data(payload)
        changed_entities = set()

        for register, value in parsed_data.items():
            name = self._register_to_name.get(register)
            if name:
                if self._data_dict.get(name) != value:
                    self._data_dict[name] = value
                    if name in self._entities:
                        changed_entities.add(name)

        for name in changed_entities:
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()

        self._reset_notify_clear_timer()

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle writes."""
        if isinstance(value, (int, float)):
            info = self.parser.protocol_data.get("registers", {}).get(cmd, {})
            scale = info.get("scale", 1.0)
            write_command = info.get("write_command", 10)
            if isinstance(value, float):
                value = int(value / scale)
            data = self.parser.pack_data(self.slave_id, cmd, value, write_command)
            await self.mqtt_manager.publish(self.cmd_topic, data)
