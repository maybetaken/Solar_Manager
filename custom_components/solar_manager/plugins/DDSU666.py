"""ChintDDSU666 device class for Solar Manager integration.

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


class ChintDDSU666(BaseDevice):
    """ChintDDSU666 device class for Solar Manager integration."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str, id: int = 1
    ) -> None:
        """Init."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.slave_id = int(id)
        self.setup_protocol()
        self._register_to_name = {}

    async def send_config(self) -> None:
        """Send config via MQTT."""
        try:
            raw_segments = self.parser.protocol_data.get("segments", [])

            final_segments = [
                {**seg, "slave_id": self.slave_id} for seg in raw_segments
            ]

            config = {"segments": final_segments}

            await self.mqtt_manager.publish(
                self._build_topic("config"), json.dumps(config)
            )
        except Exception as e:
            _LOGGER.error("Config send failed for ChintDDSU666: %s", e)

    def setup_protocol(self) -> None:
        """Setup protocol callback."""
        self.parser.register_callback(self.handle_cmd)

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device info based on JSON definition."""
        self._register_to_name = {}
        device_info = super().unpack_device_info()

        # Iterate through registers defined in the JSON file
        for register, details in self.parser.protocol_data.get("registers", {}).items():
            name = details.get("name")
            if not name:
                continue

            self._register_to_name[register] = name
            sensor_type = details.get("sensor_type", "sensor")

            # Base entity definition
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
            elif sensor_type == "button":
                entity_def.update(
                    {
                        "register": register,
                        "write_command": details.get("write_command", 6),
                        "payload_press": details.get("write_value", 1),
                    }
                )
                if "button" not in device_info:
                    device_info["button"] = []
                device_info["button"].append(entity_def)

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
        """Handle writes (Buttons, Switches, etc)."""
        info = self.parser.protocol_data.get("registers", {}).get(cmd, {})
        write_command = info.get("write_command", 6)

        val_to_write = 0

        if isinstance(value, (int, float)):
            scale = info.get("scale", 1.0)
            if isinstance(value, float):
                val_to_write = int(value / scale)
            else:
                val_to_write = int(value)
        else:
            _LOGGER.warning("Received invalid value type for command: %s", value)
            return

        data = self.parser.pack_data(self.slave_id, cmd, val_to_write, write_command)
        await self.mqtt_manager.publish(self.cmd_topic, data)
