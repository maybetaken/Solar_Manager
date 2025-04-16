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

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)

SPECIAL_REGISTERS = {
    "0x20": "scheduled_force_charge_start_time",
    "0x21": "scheduled_force_charge_end_time",
    "0x22": "scheduled_force_discharge_start_time",
    "0x23": "scheduled_force_discharge_end_time",
}


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
        self._register_to_name = {}
        self._unknown_registers = set()

    def setup_protocol(self) -> None:
        """Set up Modbus protocol parameters."""
        self.parser.register_callback(self.handle_cmd)

    async def async_setup(self) -> None:
        """Set up the device and send initial network_time."""
        await super().async_setup()
        await self._send_network_time()

    async def _send_network_time(self) -> None:
        """Send the current time to the device's network_time register (0x1E)."""
        try:
            dt = dt_util.now()
            year = dt.year - 2024
            month = dt.month
            day = dt.day
            hour = dt.hour
            minute = dt.minute
            second = dt.second
            if not (0 <= year <= 63 and 1 <= month <= 12 and 1 <= day <= 31):
                _LOGGER.error(
                    "Invalid datetime components for network_time: year=%s, month=%s, day=%s",
                    year + 2024,
                    month,
                    day,
                )
                return
            packed_value = (
                (year & 0x3F) << 26
                | (month & 0xF) << 22
                | (day & 0x1F) << 17
                | (hour & 0x1F) << 12
                | (minute & 0x3F) << 6
                | (second & 0x3F)
            )
            topic = f"{self.sn}/{self.model}/{self.slave_id}"
            data = f"1E{packed_value:07X}"
            _LOGGER.error("Sending network_time to %s: %s", topic, data)
            await self.mqtt_manager.publish(topic, data)
        except Exception as e:
            _LOGGER.error("Failed to send network_time: %s", e)

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        self.slave_id = int(self.parser.protocol_data["slave_id"])
        self.read_command = int(self.parser.protocol_data["read_command"])
        self.write_command = int(self.parser.protocol_data["write_command"])
        self.total_length = int(self.parser.protocol_data["register_total_length"])
        self.start_address = int(self.parser.protocol_data["register_start_address"])

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
            sensor_type = (
                Platform.TIME
                if register in SPECIAL_REGISTERS
                else details.get("sensor_type", "sensor")
            )

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
                        "register": register,
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
                            "register": register,
                        }
                    )

            elif sensor_type == "switch":
                device_info["switch"].append(
                    {
                        "name": name,
                        "icon": details.get("icon", None),
                        "device": self,
                        "register": register,
                    }
                )

            elif sensor_type == Platform.TIME:
                device_info[Platform.TIME] = device_info.get(Platform.TIME, [])
                device_info[Platform.TIME].append(
                    {
                        "name": name,
                        "icon": details.get("icon"),
                        "device": self,
                        "register": register,
                    }
                )
                _LOGGER.debug(
                    "Added time entity for register %s: name=%s", register, name
                )

        _LOGGER.debug(
            "Device info entries: time=%s", device_info.get(Platform.TIME, [])
        )
        return device_info

    async def handle_notify(self, topic: str, payload: str) -> None:
        """Handle MQTT notifications for Modbus data."""
        _LOGGER.debug("Received MQTT payload on topic %s: %s", topic, payload)
        parsed_data = self.parser.parse_data(payload, self.start_address)
        _LOGGER.debug("Parsed data keys: %s", list(parsed_data.keys()))
        for register in list(parsed_data.keys()):
            if register == "0x1E":
                _LOGGER.debug("Skipping network_time register %s", register)
                parsed_data.pop(register)
                continue
            if register in SPECIAL_REGISTERS:
                name = SPECIAL_REGISTERS[register]
                value = parsed_data.pop(register)
                processed_value = self._process_special_register(register, value)
                self._data_dict[name] = processed_value
                _LOGGER.debug(
                    "Processed special register %s (%s): %s",
                    register,
                    name,
                    processed_value,
                )
                entity = self._entities.get(name)
                if entity is not None:
                    entity.schedule_update_ha_state()
        regular_data = {}
        for register, value in parsed_data.items():
            name = self._register_to_name.get(register)
            if name:
                regular_data[name] = value
            elif register not in self._unknown_registers:
                _LOGGER.warning("No name found for register %s", register)
                self._unknown_registers.add(register)
        self._data_dict.update(regular_data)

        for name in regular_data:
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()

        self._reset_clear_timer()

    def _process_special_register(self, register: str, value: Any) -> Any:
        """Process a single special register and return the processed value."""
        if not isinstance(value, int):
            _LOGGER.error(
                "Invalid value type for register %s: %s", register, type(value)
            )
            return None

        _LOGGER.debug("Processing register %s with raw value: 0x%04X", register, value)

        # Scheduled times (UINT16): 0x20, 0x21, 0x22, 0x23
        hour = (value >> 11) & 0x1F
        minute = (value >> 5) & 0x3F
        interval_days = value & 0x1F
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= interval_days <= 31):
            _LOGGER.error(
                "Invalid time for register %s: hour=%s, minute=%s, interval_days=%s",
                register,
                hour,
                minute,
                interval_days,
            )
            return None
        if hour == 0 and minute == 0:
            _LOGGER.debug("Time unset for register %s: hour=0, minute=0", register)
            return None
        try:
            from datetime import time

            time_str = time(hour, minute).strftime("%H:%M")
            processed = {"time": time_str, "interval_days": interval_days}
            _LOGGER.debug("Processed scheduled time for %s: %s", register, processed)
            return processed
        except ValueError as e:
            _LOGGER.error("Invalid time for register %s: %s", register, e)
            return None

    async def handle_cmd(self, cmd: str, value: Any) -> None:
        """Handle commands from the user."""
        _LOGGER.debug("Handling command: cmd=%s, value=%s", cmd, value)
        topic = self.sn
        data: Any = None
        if isinstance(value, str):
            topic += "/" + cmd
            data = value
        elif isinstance(value, int):
            topic += "/" + self.model + "/" + str(self.slave_id)
            data = self.parser.pack_data(self.slave_id, int(cmd, 16), value)
        elif isinstance(value, float):
            topic += "/" + self.model + "/" + str(self.slave_id)
            scale = (
                self.parser.protocol_data.get("registers", {})
                .get(cmd, {})
                .get("scale", 1.0)
            )
            data = self.parser.pack_data(
                self.slave_id,
                int(cmd, 16),
                int(value / scale),
            )
        else:
            _LOGGER.error("Unsupported value type: %s", type(value))
            return
        _LOGGER.debug("Publishing to topic %s: %s", topic, data)
        await self.mqtt_manager.publish(topic, data)
