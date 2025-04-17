"""MakeSkyBlue device class for Solar Manager integration.

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

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)

SPECIAL_REGISTERS: dict[int, str] = {
    0x20: "scheduled_force_charge_start_time",
    0x21: "scheduled_force_charge_end_time",
    0x22: "scheduled_force_discharge_start_time",
    0x23: "scheduled_force_discharge_end_time",
}

# Voltage ranges for registers 8 and 9 based on platform
voltage_ranges = {
    "72V": {
        "reg8": (60.0, 70.5),
        "reg9": (72.0, 84.0),
    },
    "48V": {
        "reg8": (40.0, 47.0),
        "reg9": (48.0, 56.0),
    },
    "24V": {
        "reg8": (20.0, 23.5),
        "reg9": (24.0, 28.0),
    },
    "12V": {
        "reg8": (10.0, 11.7),
        "reg9": (12.0, 14.0),
    },
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
        self._register_to_name = {}
        self._unknown_registers = set()
        self._rate_voltage_factory = None
        self.cmd_topic = f"{self.sn}/control/cmd"

    async def send_config(self) -> None:
        """Send MakeSkyBlue-specific configuration to the device."""
        try:
            # 构造配置数据
            config_data = {
                "slave_id": self.slave_id,
                "read_command": self.read_command,
                "write_command": self.write_command,
                "segments": self.parser.protocol_data.get("segments", []),
            }
            topic = f"{self.sn}/config"
            payload = json.dumps(config_data)
            await self.mqtt_manager.publish(topic, payload)
            _LOGGER.debug("Sent config to %s: %s", topic, payload)
            await self._send_network_time()
        except Exception as e:
            _LOGGER.error("Failed to send config for %s: %s", self.sn, e)

    def setup_protocol(self) -> None:
        """Set up Modbus protocol parameters."""
        self.parser.register_callback(self.handle_cmd)

    async def async_setup(self) -> None:
        """Set up the device and send initial network_time."""
        await super().async_setup()
        await self._send_network_time()

    async def _send_network_time(self) -> None:
        """Send the current time to the device's network_time register (0x1E) in two parts."""
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
            # Pack: Bit31~26: Year, Bit25~22: Month, Bit21~17: Day
            # Bit16~12: Hour, Bit11~6: Minute, Bit5~0: Second
            packed_value = (
                (year & 0x3F) << 26
                | (month & 0xF) << 22
                | (day & 0x1F) << 17
                | (hour & 0x1F) << 12
                | (minute & 0x3F) << 6
                | (second & 0x3F)
            )
            high_bytes = (packed_value >> 16) & 0xFFFF
            low_bytes = packed_value & 0xFFFF

            await self.mqtt_manager.publish(
                self.cmd_topic, self.parser.pack_data(self.slave_id, 0x1E, high_bytes)
            )
            await self.mqtt_manager.publish(
                self.cmd_topic, self.parser.pack_data(self.slave_id, 0x1F, low_bytes)
            )

        except Exception as e:
            _LOGGER.error("Failed to send network_time: %s", e)

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        self.slave_id = int(self.parser.protocol_data["slave_id"])
        self.read_command = int(self.parser.protocol_data["read_command"])
        self.write_command = int(self.parser.protocol_data["write_command"])

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

    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle MQTT notifications for Modbus data in TLD format."""

        changed_entities = set()

        parsed_data = self.parser.parse_data(payload)
        _LOGGER.debug("Parsed data keys: %s", list(parsed_data.keys()))

        # Check if register 7 (battery_rated_voltage) is updated
        register_7 = 0x07
        if register_7 in parsed_data:
            rated_voltage_raw = parsed_data[register_7]
            if rated_voltage_raw != self._rate_voltage_factory:
                self._rate_voltage_factory = rated_voltage_raw
                # Map raw value to voltage using enum
                enum_mapping = self.parser.protocol_data["registers"][register_7][
                    "enum"
                ]
                rated_voltage = None
                for key, value in enum_mapping.items():
                    if (
                        int(key, 16)
                        == rated_voltage_raw
                        * self.parser.protocol_data["registers"][register_7]["scale"]
                    ):
                        rated_voltage = value
                        break
                if rated_voltage is None:
                    _LOGGER.error("Invalid rated voltage value: %s", rated_voltage_raw)
                else:
                    _LOGGER.debug("Detected rated voltage: %s", rated_voltage)
                    # Update ranges for registers 8 and 9
                    for reg, entity_name in [
                        (8, "battery_discharge_min_voltage"),
                        (9, "battery_start_discharge_voltage"),
                    ]:
                        entity = self._entities.get(entity_name)
                        if entity and rated_voltage in voltage_ranges:
                            reg_key = f"reg{reg}"
                            min_value, max_value = voltage_ranges[rated_voltage][
                                reg_key
                            ]
                            # Update entity attributes (assuming entity supports dynamic range updates)
                            entity._attr_native_min_value = min_value
                            entity._attr_native_max_value = max_value
                            _LOGGER.debug(
                                "Updated range for %s (register %s): min=%s, max=%s",
                                entity_name,
                                reg,
                                min_value,
                                max_value,
                            )
                            changed_entities.add(entity_name)

        for register, value in parsed_data.items():
            if register in SPECIAL_REGISTERS:
                name = SPECIAL_REGISTERS[register]
                processed_value = self._process_special_register(register, value)
                if processed_value is not None:
                    if self._data_dict.get(name) != processed_value:
                        self._data_dict[name] = processed_value
                        _LOGGER.debug(
                            "Updated special register %s (%s): %s",
                            register,
                            name,
                            processed_value,
                        )
                        if name in self._entities:
                            changed_entities.add(name)
            else:
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

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle commands from the user."""
        _LOGGER.debug("Handling command: cmd=%s, value=%s", cmd, value)
        data: Any = None

        if isinstance(value, str):
            data = value
        elif isinstance(value, int):
            data = self.parser.pack_data(self.slave_id, cmd, value)
        elif isinstance(value, float):
            scale = (
                self.parser.protocol_data.get("registers", {})
                .get(cmd, {})
                .get("scale", 1.0)
            )
            data = self.parser.pack_data(
                self.slave_id,
                cmd,
                int(value / scale),
            )
        else:
            _LOGGER.error("Unsupported value type: %s", type(value))
            return
        _LOGGER.debug("Publishing to topic %s: %s", self.cmd_topic, data)
        await self.mqtt_manager.publish(self.cmd_topic, data)
