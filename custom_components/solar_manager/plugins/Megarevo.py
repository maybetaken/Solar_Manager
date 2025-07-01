"""Megarevo device class for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import json
import logging
from typing import Any, Tuple

from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)

buttons: dict[str, int] = {
    "restore_factory_setting": 0x3416,
    "clear_record": 0x3417,
    "clear_statistical": 0x341D,
    "clear_arc_alarm": 0x3429,
}

# Time-related register mappings
TIME_BASE_REGISTERS: dict[int, Tuple[str, str, Tuple[int, int, int, int]]] = {
    0x303500: (
        "year",
        "month",
        (0, 99, 1, 12),
    ),  # High: year offset (0-99, 2000+), Low: month (1-12)
    0x303501: ("day", "unused", (1, 31, 0, 0)),  # High: day (1-31), Low: unused (0)
    0x303502: (
        "hour",
        "minute",
        (0, 23, 0, 59),
    ),  # High: hour (0-23), Low: minute (0-59)
    0x303503: ("second", "week", (0, 59, 1, 7)),  # High: second (0-59), Low: week (1-7)
}
TIME_SCHEDULE_REGISTERS: dict[int, str] = {
    0x303504: "charge_time1_start",
    0x303505: "charge_time1_end",
    0x303506: "discharge_time1_start",
    0x303507: "discharge_time1_end",
    0x303508: "charge_time2_start",
    0x303509: "charge_time2_end",
    0x30350A: "discharge_time2_start",
    0x30350B: "discharge_time2_end",
    0x30350C: "charge_time3_start",
    0x30350D: "charge_time3_end",
    0x30350E: "discharge_time3_start",
    0x30350F: "discharge_time3_end",
}

# Special registers requiring high/low 16-bit swap
SPECIAL_REGISTERS = range(0x303153, 0x303182)  # 0x3153 to 0x3181 inclusive


def swap_16_bits(value: int) -> int:
    """Swap high and low 16 bits of a 32-bit integer."""
    high_16 = (value >> 16) & 0xFFFF
    low_16 = value & 0xFFFF
    return (low_16 << 16) | high_16


class Megarevo(BaseDevice):
    """Megarevo device class for Solar Manager integration."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the Megarevo device."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.setup_protocol()
        self.slave_id = 1
        self._register_to_name = {
            **{r: n for r, (n, _, _) in TIME_BASE_REGISTERS.items() if n != "unused"},
            **{r: n for r, n in TIME_SCHEDULE_REGISTERS.items()},
        }
        self._unknown_registers = set()
        self.cmd_topic = f"{self.sn}/control/cmd"

    async def send_config(self) -> None:
        """Send device-specific configuration to the device."""
        try:
            config_data = {
                "segments": self.parser.protocol_data.get("segments", []),
            }
            topic = f"{self.sn}/config"
            payload = json.dumps(config_data)
            await self.mqtt_manager.publish(topic, payload)
            _LOGGER.debug("Sent config to %s: %s", topic, payload)
        except Exception as e:
            _LOGGER.error("Failed to send config for %s: %s", self.sn, e)

    def setup_protocol(self) -> None:
        """Set up Modbus protocol parameters."""
        self.parser.register_callback(self.handle_cmd)

    async def async_setup(self) -> None:
        """Set up the device."""
        await super().async_setup()

    async def perform_action(self, action_name: str) -> None:
        """Perform an action based on the action name."""
        await super().perform_action(action_name)

        if action_name in buttons:
            register = buttons.get(action_name)
            await self.handle_cmd(register, 1)

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

        # Original sensor type handling
        for register, details in self.parser.protocol_data.get("registers", {}).items():
            name = details.get("name")
            if not name or not isinstance(name, str) or not name.strip():
                _LOGGER.error(
                    "Skipping register %s: invalid or missing name: %s", register, name
                )
                continue

            sensor_type = details.get("sensor_type", "sensor")

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

            elif sensor_type == "button":
                device_info["button"].append(
                    {
                        "name": name,
                        "icon": details.get("icon", None),
                        "device": self,
                        "register": register,
                    }
                )

        # Add time-related entities
        device_info["number"].append(
            {
                "name": "year",
                "scale": 1.0,
                "min_value": 0,
                "max_value": 99,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:calendar",
                "device": self,
                "register": 0x303500,
            }
        )
        device_info["number"].append(
            {
                "name": "month",
                "scale": 1.0,
                "min_value": 1,
                "max_value": 12,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:calendar-month",
                "device": self,
                "register": 0x303500,
            }
        )
        device_info["number"].append(
            {
                "name": "day",
                "scale": 1.0,
                "min_value": 1,
                "max_value": 31,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:calendar-today",
                "device": self,
                "register": 0x303501,
            }
        )
        device_info["number"].append(
            {
                "name": "hour",
                "scale": 1.0,
                "min_value": 0,
                "max_value": 23,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:clock",
                "device": self,
                "register": 0x303502,
            }
        )
        device_info["number"].append(
            {
                "name": "minute",
                "scale": 1.0,
                "min_value": 0,
                "max_value": 59,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:clock",
                "device": self,
                "register": 0x303502,
            }
        )
        device_info["number"].append(
            {
                "name": "second",
                "scale": 1.0,
                "min_value": 0,
                "max_value": 59,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:clock",
                "device": self,
                "register": 0x303503,
            }
        )
        device_info["number"].append(
            {
                "name": "week",
                "scale": 1.0,
                "min_value": 1,
                "max_value": 7,
                "unit": None,
                "step": 1,
                "display_precision": 0,
                "icon": "mdi:calendar-week",
                "device": self,
                "register": 0x303503,
            }
        )
        for register, name in TIME_SCHEDULE_REGISTERS.items():
            device_info[Platform.TIME] = device_info.get(Platform.TIME, [])
            device_info["time"].append(
                {
                    "name": name,
                    "icon": "mdi:clock" if "start" in name else "mdi:clock-end",
                    "device": self,
                    "register": register,
                }
            )

        return device_info

    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle MQTT notifications for Modbus data in TLD format."""
        changed_entities = set()

        parsed_data = self.parser.parse_data(payload)
        _LOGGER.debug("Parsed data keys: %s", list(parsed_data.keys()))

        # Handle time base registers
        await self._process_time_base_registers(parsed_data, changed_entities)

        # Handle time schedule registers
        await self._process_time_schedule_registers(parsed_data, changed_entities)

        # Handle original registers
        for register, value in parsed_data.items():
            if register not in {**TIME_BASE_REGISTERS, **TIME_SCHEDULE_REGISTERS}:
                name = self._register_to_name.get(register)
                if name:
                    # Special handling for registers 0x3153 to 0x3181 (swap high/low 16 bits)
                    if register in SPECIAL_REGISTERS:
                        # Swap high and low 16 bits
                        corrected_value = swap_16_bits(value)
                        # Update only if value has changed
                        if self._data_dict.get(name) != corrected_value:
                            self._data_dict[name] = corrected_value
                            _LOGGER.debug(
                                "Updated register %s (%s): %s (swapped from %s)",
                                hex(register),
                                name,
                                corrected_value,
                                value,
                            )
                            if name in self._entities:
                                changed_entities.add(name)
                    else:
                        # Normal handling for other registers
                        if self._data_dict.get(name) != value:
                            self._data_dict[name] = value
                            _LOGGER.debug(
                                "Updated register %s (%s): %s",
                                hex(register),
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

    async def _process_time_base_registers(
        self, parsed_data: dict, changed_entities: set
    ) -> None:
        """Process time base registers (0x303500-0x303503)."""
        for register, (
            high_name,
            low_name,
            (high_min, high_max, low_min, low_max),
        ) in TIME_BASE_REGISTERS.items():
            if register in parsed_data:
                current_value = parsed_data[register]
                # Check if the register value has changed
                if self._data_dict.get(register) == current_value:
                    continue
                high_value = (current_value >> 8) & 0xFF
                low_value = current_value & 0xFF

                # Validate and store high byte
                if high_name != "unused":
                    if not (high_min <= high_value <= high_max):
                        _LOGGER.error(
                            "Invalid %s value %s for register %s",
                            high_name,
                            high_value,
                            hex(register),
                        )
                        continue
                    if self._data_dict.get(high_name) != high_value:
                        self._data_dict[high_name] = high_value
                        _LOGGER.debug(
                            "Updated %s (register %s high): %s",
                            high_name,
                            hex(register),
                            high_value,
                        )
                        if high_name in self._entities:
                            changed_entities.add(high_name)

                # Validate and store low byte
                if not (low_min <= low_value <= low_max):
                    _LOGGER.error(
                        "Invalid %s value %s for register %s",
                        low_name,
                        low_value,
                        hex(register),
                    )
                    continue
                if self._data_dict.get(low_name) != low_value:
                    self._data_dict[low_name] = low_value
                    _LOGGER.debug(
                        "Updated %s (register %s low): %s",
                        low_name,
                        hex(register),
                        low_value,
                    )
                    if low_name in self._entities:
                        changed_entities.add(low_name)

                # Store the raw register value for future comparison
                self._data_dict[register] = current_value

                # Trigger update for all time schedule entities due to base change
                for sched_name in TIME_SCHEDULE_REGISTERS.values():
                    if sched_name in self._entities:
                        changed_entities.add(sched_name)

    async def _process_time_schedule_registers(
        self, parsed_data: dict, changed_entities: set
    ) -> None:
        """Process time schedule registers (0x303504-0x30350F)."""
        for register, name in TIME_SCHEDULE_REGISTERS.items():
            if register in parsed_data:
                current_value = parsed_data[register]
                # Check if the register value has changed
                if self._data_dict.get(register) == current_value:
                    continue
                # Convert HHMM decimal to hour and minute
                hour = current_value // 100
                minute = current_value % 100
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    _LOGGER.error(
                        "Invalid time value %s for register %s",
                        current_value,
                        hex(register),
                    )
                    continue
                time_str = f"{hour:02d}:{minute:02d}"
                if self._data_dict.get(name) != time_str:
                    self._data_dict[name] = time_str
                    _LOGGER.debug(
                        "Updated schedule register %s (%s): %s",
                        hex(register),
                        name,
                        time_str,
                    )
                    if name in self._entities:
                        changed_entities.add(name)

                # Store the raw register value for future comparison
                self._data_dict[register] = current_value

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle commands from the user."""
        _LOGGER.debug("Handling command: cmd=%s, value=%s", hex(cmd), value)

        data: Any = None

        # Handle time base registers
        if cmd in TIME_BASE_REGISTERS:
            data = await self._handle_time_base_cmd(cmd, value)

        # Handle time schedule registers
        elif cmd in TIME_SCHEDULE_REGISTERS:
            data = await self._handle_time_schedule_cmd(cmd, value)

        # Handle original registers
        else:
            if isinstance(value, str):
                data = value
            elif isinstance(value, (int, float)):
                scale = (
                    self.parser.protocol_data.get("registers", {})
                    .get(cmd, {})
                    .get("scale", 1.0)
                )
                if isinstance(value, float):
                    value = int(value / scale)
                data = self.parser.pack_data(self.slave_id, cmd, value)
            else:
                _LOGGER.error("Unsupported value type: %s", type(value))
                return

        if data is not None:
            _LOGGER.debug("Publishing to topic %s: %s", self.cmd_topic, data)
            await self.mqtt_manager.publish(self.cmd_topic, data)

        # Update data dictionary and entity state for non-time registers
        entity_name = self._register_to_name.get(cmd)
        if (
            entity_name
            and entity_name in self._entities
            and cmd not in {**TIME_BASE_REGISTERS, **TIME_SCHEDULE_REGISTERS}
        ):
            self._data_dict[entity_name] = value
            self._entities[entity_name].schedule_update_ha_state()

    async def _handle_time_base_cmd(self, cmd: int, value: Any) -> Any:
        """Handle commands for time base registers (0x303500-0x303503)."""
        high_name, low_name, (high_min, high_max, low_min, low_max) = (
            TIME_BASE_REGISTERS[cmd]
        )
        if isinstance(value, dict) and "high" in value and "low" in value:
            high_value = value["high"]
            low_value = value["low"]
        else:
            _LOGGER.error("Invalid value format for register %s: %s", hex(cmd), value)
            return None

        # Validate high byte
        if high_name != "unused":
            if not isinstance(high_value, int) or not (
                high_min <= high_value <= high_max
            ):
                _LOGGER.error(
                    "Invalid %s value %s for register %s",
                    high_name,
                    high_value,
                    hex(cmd),
                )
                return None
        else:
            high_value = 0

        # Validate low byte
        if not isinstance(low_value, int) or not (low_min <= low_value <= low_max):
            _LOGGER.error(
                "Invalid %s value %s for register %s", low_name, low_value, hex(cmd)
            )
            return None

        packed_value = (high_value << 8) | low_value
        data = self.parser.pack_data(self.slave_id, cmd, packed_value)
        if high_name != "unused":
            self._data_dict[high_name] = high_value
        self._data_dict[low_name] = low_value
        # Store the raw register value for future comparison
        self._data_dict[cmd] = packed_value
        # Trigger update for all time schedule entities
        for name in TIME_SCHEDULE_REGISTERS.values():
            if name in self._entities:
                self._entities[name].schedule_update_ha_state()
        return data

    async def _handle_time_schedule_cmd(self, cmd: int, value: Any) -> Any:
        """Handle commands for time schedule registers (0x303504-0x30350F)."""
        if isinstance(value, str):
            try:
                hour, minute = map(int, value.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
                # Convert to HHMM decimal
                packed_value = hour * 100 + minute
                data = self.parser.pack_data(self.slave_id, cmd, packed_value)
                self._data_dict[TIME_SCHEDULE_REGISTERS[cmd]] = value
            except (ValueError, AttributeError):
                _LOGGER.error("Invalid time value for %s: %s", hex(cmd), value)
                return None
        elif isinstance(value, int):
            hour = (value >> 8) & 0xFF
            minute = value & 0xFF
            packed_value = hour * 100 + minute
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                _LOGGER.error("Invalid time value for %s: %s", hex(cmd), value)
                return None
            data = self.parser.pack_data(self.slave_id, cmd, packed_value)
            self._data_dict[TIME_SCHEDULE_REGISTERS[cmd]] = f"{hour:02d}:{minute:02d}"
        if data is not None:
            # Store the raw register value for future comparison
            self._data_dict[cmd] = packed_value
        return data
