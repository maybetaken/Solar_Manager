"""MakeSkyBlue device class for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import logging
from typing import Any

from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)

from homeassistant.core import HomeAssistant

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)


class MakeSkyBlueDevice(BaseDevice):
    """MakeSkyBlue device class for Solar Manager."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the base device."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.setup_protocol()
        self.slave_id = 1
        self.read_command = 3
        self.write_command = 6
        self.total_length = 217
        self.start_address = 0

    def setup_protocol(self) -> None:
        """Set up Modbus protocol parameters."""
        self.parser.register_callback(self.handle_cmd)

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        self.slave_id = int(self.parser.protocol_data["slave_id"])
        self.read_command = int(self.parser.protocol_data["read_command"])
        self.write_command = int(self.parser.protocol_data["write_command"])
        self.total_length = int(self.parser.protocol_data["register_total_length"])
        self.start_address = int(self.parser.protocol_data["register_start_address"])

        device_info = super().unpack_device_info()

        for register, details in self.protocol_data["registers"].items():
            name = details["name"]
            sensor_type = details.get("sensor_type")

            if sensor_type == "sensor":
                if "enum" in details:
                    enum_mapping = {
                        int(key, 16) if key.startswith("0x") else int(key): value
                        for key, value in details["enum"].items()
                    }
                    device_info["sensor"].append(
                        {
                            "name": name,
                            "scale": details.get("scale", 1.0),
                            "enum_mapping": enum_mapping,
                            "icon": details.get("icon"),
                            "device": self,
                        }
                    )
                else:
                    device_info["sensor"].append(
                        {
                            "name": name,
                            "scale": details.get("scale", 1.0),
                            "unit": details.get("unit"),
                            "icon": details.get("icon"),
                            "display_precision": details.get("display_precision", 0),
                            "device": self,
                        }
                    )

            elif sensor_type == "number":
                device_info["number"].append(
                    {
                        "name": name,
                        "scale": details.get("scale", 1.0),
                        "min_value": details.get("min_value"),
                        "max_value": details.get("max_value"),
                        "unit": details.get("unit"),
                        "step": details.get("step", details.get("scale", 1.0)),
                        "display_precision": details.get("display_precision", 0),
                        "icon": details.get("icon"),
                        "device": self,
                        "register": register,  # Still needed for write operations
                    }
                )

            elif sensor_type == "select":
                if "enum" in details:
                    options = list(details["enum"].values())
                    device_info["select"].append(
                        {
                            "name": name,
                            "options": options,
                            "enum_mapping": {
                                int(key, 16)
                                if key.startswith("0x")
                                else int(key): value
                                for key, value in details["enum"].items()
                            },
                            "device": self,
                            "register": register,  # Still needed for write operations
                        }
                    )

            elif sensor_type == "switch":
                device_info["switch"].append(
                    {
                        "name": name,
                        "icon": details.get("icon", None),
                        "device": self,
                        "register": register,  # Still needed for write operations
                    }
                )

        return device_info

    async def handle_notify(self, topic: str, payload: str) -> None:
        """Handle MQTT notifications for Modbus data."""
        parsed_data = self.parser.parse_data(payload, self.start_address)
        # Additional processing of parsed data
        processed_data = self._process_parsed_data(parsed_data)
        # Store in data_dict
        self._data_dict.update(processed_data)
        _LOGGER.debug("Updated data_dict for %s: %s", self.sn, self._data_dict)
        # Reset clear timer
        self._reset_clear_timer()
        # Update only affected entities
        for name in processed_data:
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()

    def _process_parsed_data(self, parsed_data: dict) -> dict:
        """Additional processing of parsed data before storing."""
        # Create a lookup table for register details by name
        register_details = {
            details["name"]: details
            for _, details in self.protocol_data["registers"].items()
        }
        processed = {}
        for name, value in parsed_data.items():
            # details = register_details.get(name)
            processed[name] = value  # No processing if details not found
        return processed

    async def handle_cmd(self, cmd: str, value: any) -> None:
        """Handle commands from the user."""
        topic = self.sn
        data: any = None
        if isinstance(value, str):
            topic += "/" + cmd
            data = value
        elif isinstance(value, int):
            topic += "/" + self.model + "/" + str(self.slave_id)
            data = self.parser.pack_data(self.slave_id, int(cmd, 16), value)
        elif isinstance(value, float):
            topic += "/" + self.model + "/" + str(self.slave_id)
            scale = self.protocol_data["registers"][cmd].get("scale", 1.0)
            data = self.parser.pack_data(
                self.slave_id,
                int(cmd, 16),
                int(value / scale),
            )
        else:
            _LOGGER.error("Unsupported value type: %s", type(value))
            return

        await self.mqtt_manager.publish(topic, data)
