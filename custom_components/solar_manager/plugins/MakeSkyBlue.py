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
    0x300020: "scheduled_force_charge_start_time",
    0x300021: "scheduled_force_charge_end_time",
    0x300022: "scheduled_force_discharge_start_time",
    0x300023: "scheduled_force_discharge_end_time",
}

PSEUDO_REGISTERS: dict[int, tuple[str, int]] = {
    0x10020: ("force_charge_interval", 0x300020),  # Maps to real register 0x20
    0x10022: ("force_discharge_interval", 0x300022),  # Maps to real register 0x22
}

voltage_ranges = {
    "72v": {
        0x300008: (60.0, 70.5),
        0x300009: (72.0, 88.0),
    },
    "48v": {
        0x300008: (40.0, 47.0),
        0x300009: (48.0, 56.0),
    },
    "24v": {
        0x300008: (20.0, 23.5),
        0x300009: (24.0, 28.0),
    },
    "12v": {
        0x300008: (10.0, 11.7),
        0x300009: (12.0, 14.0),
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
        self._register_to_name = {}
        self._unknown_registers = set()
        self._rate_voltage_factory = None
        self._inverter_ac_voltage_initial = None

    async def send_config(self) -> None:
        """Send MakeSkyBlue-specific configuration to the device."""
        try:
            config_data = {
                "segments": self.parser.protocol_data.get("segments", []),
            }
            topic = self._build_topic("config")
            payload = json.dumps(config_data)
            await self.mqtt_manager.publish(topic, payload)
            _LOGGER.debug("Sent config to %s: %s", topic, payload)
            await self._send_network_time()
        except Exception as e:
            _LOGGER.error("Failed to send config for %s: %s", self.sn, e)

    def setup_protocol(self) -> None:
        """Set up Modbus protocol parameters."""
        self.parser.register_callback(self.handle_cmd)

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
                            "offset": details.get("offset", 0),
                            "device_class": details.get("device_class", "None"),
                            "state_class": details.get("state_class", "None"),
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

        device_info["sensor"].append(
            {
                "name": "inverter_factor",
                "scale": 0.01,
                "icon": "mdi:angle-acute",
                "display_precision": 2,
                "device": self,
            }
        )

        device_info["number"].append(
            {
                "name": "force_charge_interval",
                "scale": 1,
                "min_value": 0,
                "max_value": 31,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:timer-sync",
                "device": self,
                "register": 0x10020,
            }
        )

        device_info["number"].append(
            {
                "name": "force_discharge_interval",
                "scale": 1,
                "min_value": 0,
                "max_value": 31,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:timer-sync",
                "device": self,
                "register": 0x10022,
            }
        )
        return device_info

    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle MQTT notifications for Modbus data in TLD format."""
        changed_entities = set()

        parsed_data = self.parser.parse_data(payload)
        _LOGGER.debug("Parsed data keys: %s", list(parsed_data.keys()))

        # Check if register 2 (inverter_ac_voltage) is updated for the first time
        register_2 = 0x300002
        if register_2 in parsed_data and self._inverter_ac_voltage_initial is None:
            inverter_ac_voltage = parsed_data[register_2]
            self._inverter_ac_voltage_initial = inverter_ac_voltage

        # Check if register 7 (battery_rated_voltage) is updated
        register_7 = 0x300007
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
                        (0x300008, "battery_discharge_min_voltage"),
                        (0x300009, "battery_start_discharge_voltage"),
                    ]:
                        entity = self._entities.get(entity_name)
                        if entity and rated_voltage in voltage_ranges:
                            min_value, max_value = voltage_ranges[rated_voltage][reg]
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

        register_145 = 0x300091
        if register_145 in parsed_data:
            value = parsed_data[register_145]
            name = self._register_to_name.get(register_145)
            if name and isinstance(value, int):
                major = (value >> 10) & 0x3
                minor = (value >> 6) & 0x0F
                patch = value & 0x3F
                version_str = f"V{major}.{minor}.{patch}"
                if self._data_dict.get(name) != version_str:
                    self._data_dict[name] = version_str
                    _LOGGER.debug(
                        "Updated software version (register %s): %s",
                        register_145,
                        version_str,
                    )
                    if name in self._entities:
                        changed_entities.add(name)
            del parsed_data[register_145]

        register_6e = 0x30006E
        if register_6e in parsed_data:
            power_factor_combined = parsed_data[register_6e]
            inverter_factor = (power_factor_combined >> 8) & 0xFF
            power_factor = power_factor_combined & 0xFF

            if self._data_dict.get("inverter_factor") != inverter_factor:
                self._data_dict["inverter_factor"] = inverter_factor
                changed_entities.add("inverter_factor")
                _LOGGER.debug("Updated inverter_factor: %s", inverter_factor)

            if self._data_dict.get("power_factor") != power_factor:
                self._data_dict["power_factor"] = power_factor
                changed_entities.add("power_factor")
                _LOGGER.debug("Updated power_factor: %s", power_factor)
            del parsed_data[register_6e]

        for register, value in parsed_data.items():
            if register in SPECIAL_REGISTERS:
                name = SPECIAL_REGISTERS[register]
                processed_value, interval_days = self._process_special_register(
                    register, value
                )
                if processed_value is not None:
                    # Store time string for time entity
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

                    # Store interval_days for corresponding interval entity
                    if register in [0x300020, 0x300022]:
                        interval_name = (
                            "force_charge_interval"
                            if register == 0x300020
                            else "force_discharge_interval"
                        )
                        if interval_days is not None and 0 <= interval_days <= 31:
                            if self._data_dict.get(interval_name) != interval_days:
                                self._data_dict[interval_name] = interval_days
                                changed_entities.add(interval_name)
                                _LOGGER.debug(
                                    "Updated %s: %s", interval_name, interval_days
                                )
                        else:
                            _LOGGER.error(
                                "Register %s invalid interval days: %s",
                                register,
                                interval_days,
                            )
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

        self._reset_notify_clear_timer()

    def _process_special_register(
        self, register: int, value: Any
    ) -> tuple[str | None, int | None]:
        """Process a single special register and return the time string and interval_days."""
        if not isinstance(value, int):
            _LOGGER.error(
                "Invalid value type for register %s: %s", register, type(value)
            )
            return None, None

        _LOGGER.debug("Processing register %s with raw value: 0x%04X", register, value)

        hour = (value >> 11) & 0x1F
        minute = (value >> 5) & 0x3F
        interval_days = value & 0x1F if register in [0x300020, 0x300022] else None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            _LOGGER.error(
                "Invalid time for register %s: hour=%s, minute=%s",
                register,
                hour,
                minute,
            )
            return None, None
        if interval_days is not None and not (0 <= interval_days <= 31):
            _LOGGER.error(
                "Invalid interval_days for register %s: %s", register, interval_days
            )
            return None, None

        try:
            from datetime import time

            time_str = time(hour, minute).strftime("%H:%M")
            _LOGGER.debug(
                "Processed scheduled time for %s: time=%s, interval_days=%s",
                register,
                time_str,
                interval_days,
            )
            return time_str, interval_days
        except ValueError as e:
            _LOGGER.error("Invalid time for register %s: %s", register, e)
            return None, None

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle commands from the user."""
        _LOGGER.debug("Handling command: cmd=%s, value=%s", cmd, value)
        data: Any = None

        # Handle time commands for registers 0x20, 0x21, 0x22, 0x23
        if cmd in [0x300020, 0x300021, 0x300022, 0x300023]:
            if not isinstance(value, int) or value > 0xFFFF:
                _LOGGER.error("Invalid time value for register %s: %s", cmd, value)
                return
            hour = (value >> 8) & 0xFF
            minute = value & 0xFF
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                _LOGGER.error(
                    "Invalid time for register %s: hour=%s, minute=%s",
                    cmd,
                    hour,
                    minute,
                )
                return
            # For registers 0x20 and 0x22, preserve existing interval_days
            interval_days = 0
            if cmd in [0x300020, 0x300022]:
                interval_name = (
                    "force_charge_interval"
                    if cmd == 0x300020
                    else "force_discharge_interval"
                )
                interval_days = self._data_dict.get(interval_name, 0)
                if not (0 <= interval_days <= 31):
                    _LOGGER.error(
                        "Invalid stored interval_days for %s: %s",
                        interval_name,
                        interval_days,
                    )
                    interval_days = 0
            # Pack the value: hour (5 bits), minute (6 bits), interval_days (5 bits)
            packed_value = (
                (hour & 0x1F) << 11
                | (minute & 0x3F) << 5
                | ((int)(interval_days) & 0x1F)
            )
            data = self.parser.pack_data(self.slave_id, cmd, packed_value)
            # Update _data_dict with time string
            time_str = f"{hour:02d}:{minute:02d}"
            entity_name = self._register_to_name.get(cmd)
            if entity_name:
                self._data_dict[entity_name] = time_str
                _LOGGER.debug("Updated %s: time=%s", entity_name, time_str)
                if entity_name in self._entities:
                    self._entities[entity_name].schedule_update_ha_state()

        # Handle interval commands for pseudo-registers 0x10020, 0x10022
        elif cmd in [0x10020, 0x10022]:
            interval_name, real_register = PSEUDO_REGISTERS.get(cmd, (None, None))
            if not interval_name or not real_register:
                _LOGGER.error("Invalid pseudo-register %s", cmd)
                return
            if not isinstance(value, int) or not (0 <= value <= 31):
                _LOGGER.error("Invalid interval_days for register %s: %s", cmd, value)
                return
            interval_days = value
            entity_name = self._register_to_name.get(real_register)
            if not entity_name:
                _LOGGER.error("No entity name found for register %s", real_register)
                return
            # Get current time from _data_dict
            time_str = self._data_dict.get(entity_name, "00:00")
            hour, minute = map(int, time_str.split(":")) if ":" in time_str else (0, 0)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                _LOGGER.error(
                    "Invalid stored time for %s (%s): %s",
                    real_register,
                    entity_name,
                    time_str,
                )
                return
            # Pack the value with existing time and new interval_days
            packed_value = (
                (hour & 0x1F) << 11 | (minute & 0x3F) << 5 | (interval_days & 0x1F)
            )
            data = self.parser.pack_data(self.slave_id, real_register, packed_value)
            # Update _data_dict for interval entity
            self._data_dict[interval_name] = interval_days
            _LOGGER.debug("Updated %s: interval_days=%s", interval_name, interval_days)
            if interval_name in self._entities:
                self._entities[interval_name].schedule_update_ha_state()

        # Validate register 2 (inverter_ac_voltage) commands
        elif cmd == 0x300002:
            if (
                self._inverter_ac_voltage_initial is not None
                and self._inverter_ac_voltage_initial >= 2
            ):
                if value < 2:
                    _LOGGER.error(
                        "Inverter AC voltage value %s not allowed; must be 208V or higher (initial value %s)",
                        value,
                        self._inverter_ac_voltage_initial,
                    )
                    return
            enum_mapping = self.parser.protocol_data["registers"][0x300002]["enum"]
            valid_value = False
            for key in enum_mapping:
                if int(key, 16) == value:
                    valid_value = True
                    break
            if not valid_value:
                _LOGGER.error("Invalid inverter_ac_voltage value: %s", value)
                return
            data = self.parser.pack_data(self.slave_id, cmd, value)

        # Handle other register types
        else:
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

        if data is not None:
            _LOGGER.debug("Publishing to topic %s: %s", self.cmd_topic, data)
            await self.mqtt_manager.publish(self.cmd_topic, data)
            if not isinstance(value, str) and cmd not in [
                0x300020,
                0x300021,
                0x300022,
                0x300023,
                0x10020,
                0x10022,
            ]:
                self._data_dict[cmd] = (
                    value if isinstance(value, int) else int(value / scale)
                )
                entity_name = self._register_to_name.get(cmd)
                if entity_name and entity_name in self._entities:
                    self._entities[entity_name].schedule_update_ha_state()
