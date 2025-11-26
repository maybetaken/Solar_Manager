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

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)

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


class MakeSkyBlueIoTrix(BaseDevice):
    """MakeSkyBlue device class for Solar Manager."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the base device."""
        super().__init__(hass, protocol_file, sn, model, "makeskyblue/iotrix")
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.setup_protocol()
        self.slave_id = 1
        self._register_to_name = {}
        self._unknown_registers = set()
        self._rate_voltage_factory = None
        self._inverter_ac_voltage_initial = None

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
                        "write_command": details.get("write_command", 6),
                    }
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

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle commands from the user."""
        _LOGGER.debug("Handling command: cmd=%s, value=%s", cmd, value)
        data: Any = None

        # Validate register 2 (inverter_ac_voltage) commands
        if cmd == 0x300002:
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
            elif isinstance(value, (int, float)):
                info = self.parser.protocol_data.get("registers", {}).get(cmd, {})
                scale = info.get("scale", 1.0)
                write_command = info.get("write_command", 6)
                if isinstance(value, float):
                    value = int(value / scale)
                data = self.parser.pack_data(self.slave_id, cmd, value, write_command)
            else:
                _LOGGER.error("Unsupported value type: %s", type(value))
                return

        if data is not None:
            _LOGGER.debug("Publishing to topic %s: %s", self.cmd_topic, data)
            await self.mqtt_manager.publish(self.cmd_topic, data)

            # Update data dictionary and entity state
            entity_name = self._register_to_name.get(cmd)
            if entity_name and entity_name in self._entities:
                self._data_dict[entity_name] = value
                self._entities[entity_name].schedule_update_ha_state()
