"""Sungrey device class for Solar Manager integration.

Copyright 2025-2026 maybetaken

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
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


class SungreyDevice(BaseDevice):
    """Read-only monitoring for Sungrey (REVO series) hybrid inverters."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the Sungrey device."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.setup_protocol()
        self.slave_id = 1
        self._register_to_name = {}
        self._unknown_registers = set()

    async def send_config(self) -> None:
        """Send device-specific configuration to the device."""
        try:
            config_data = {
                "segments": self.parser.protocol_data.get("segments", []),
            }
            topic = self._build_topic("config")
            payload = json.dumps(config_data)
            await self.mqtt_manager.publish(topic, payload)
            _LOGGER.debug("Sent config to %s: %s", topic, payload)
        except Exception as e:
            _LOGGER.error("Failed to send config for %s: %s", self.sn, e)

    def setup_protocol(self) -> None:
        """Set up Modbus protocol parameters."""
        self.parser.register_callback(self.handle_cmd)

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        self._register_to_name = {}
        for register, details in self.parser.protocol_data.get("registers", {}).items():
            name = details.get("name")
            if name and isinstance(name, str) and name.strip():
                self._register_to_name[register] = name
            else:
                _LOGGER.warning(
                    "Register %s has invalid or missing name: %s", register, name
                )

        device_info = super().unpack_device_info()

        for register, details in self.parser.protocol_data.get("registers", {}).items():
            name = details.get("name")
            if not name or not isinstance(name, str) or not name.strip():
                _LOGGER.error(
                    "Skipping register %s: invalid or missing name: %s", register, name
                )
                continue

            if details.get("sensor_type", "sensor") != "sensor":
                continue

            device_info["sensor"].append(
                {
                    "name": name,
                    "scale": details.get("scale", 1.0),
                    "unit": details.get("unit"),
                    "icon": details.get("icon"),
                    "display_precision": details.get("display_precision", 0),
                    "device": self,
                    "offset": details.get("offset", 0),
                    "device_class": details.get("device_class", None),
                    "state_class": details.get("state_class", None),
                }
            )

        return device_info

    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle MQTT notifications for Modbus data in TLD format."""
        changed_entities = set()

        parsed_data = self.parser.parse_data(payload)
        _LOGGER.debug("Parsed data keys: %s", list(parsed_data.keys()))

        for register, value in parsed_data.items():
            name = self._register_to_name.get(register)
            if name:
                if self._data_dict.get(name) != value:
                    self._data_dict[name] = value
                    _LOGGER.debug(
                        "Updated register %s (%s): %s",
                        register,
                        name,
                        value,
                    )
                    if name in self._entities:
                        changed_entities.add(name)
            elif register not in self._unknown_registers:
                _LOGGER.warning(
                    "No name found for register %s (hex format %s)",
                    register,
                    hex(register),
                )
                self._unknown_registers.add(register)

        for name in changed_entities:
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()
                _LOGGER.debug("Updated entity %s due to data change", name)

        # Reset notify clear timer
        self._reset_notify_clear_timer()

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle commands from the user (no writable registers defined)."""
        _LOGGER.debug("Handling command: cmd=%s, value=%s", cmd, value)

        if isinstance(value, (int, float)):
            data = self.parser.pack_data(self.slave_id, cmd, int(value), 6)
        elif isinstance(value, str):
            data = value
        else:
            _LOGGER.error("Unsupported value type: %s", type(value))
            return

        _LOGGER.debug("Publishing to topic %s: %s", self.cmd_topic, data)
        await self.mqtt_manager.publish(self.cmd_topic, data)
