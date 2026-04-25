"""JkBms device class for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import json
import logging
from datetime import datetime, date, time
from typing import Any
import asyncio

from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)


class JkBms(BaseDevice):
    """JkBms device class for Solar Manager integration."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str, id: int = 15
    ) -> None:
        """Init."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.slave_id = int(id)
        self.setup_protocol()
        self._register_to_name = {}
        self._unknown_registers = set()
        
        # Daily energy tracking variables
        self._daily_charge_energy = 0.0  # Daily charge energy in kWh
        self._daily_discharge_energy = 0.0  # Daily discharge energy in kWh
        self._last_update_time = None  # Last update timestamp
        self._last_power = 0.0  # Last power reading
        self._hass = hass
        self._midnight_timer = None  # Midnight timer

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

            entity_def = {
                "addressing": "byte",
                "name": name,
                "scale": details.get("scale", 1),
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
                        "step": details.get("step", 1),
                        "register": register,
                    }
                )
                device_info["number"].append(entity_def)

            elif sensor_type == "switch":
                entity_def.update(
                    {
                        "register": register,
                        "write_command": details.get("write_command", 16),
                    }
                )
                device_info["switch"].append(entity_def)

        # Add daily charge and discharge energy sensors
        daily_charge_entity = {
            "addressing": "byte",
            "name": "daily_charge_energy",
            "scale": 1.0,
            "unit": "KILOWATT_HOUR",
            "icon": "mdi:battery-charging",
            "display_precision": 3,
            "device": self,
            "offset": 0,
            "device_class": "energy",
            "state_class": "total",
        }
        device_info["sensor"].append(daily_charge_entity)

        daily_discharge_entity = {
            "addressing": "byte",
            "name": "daily_discharge_energy",
            "scale": 1.0,
            "unit": "KILOWATT_HOUR",
            "icon": "mdi:battery-minus",
            "display_precision": 3,
            "device": self,
            "offset": 0,
            "device_class": "energy",
            "state_class": "total",
        }
        device_info["sensor"].append(daily_discharge_entity)

        # Initialize daily energy tracking and setup timer
        self._setup_daily_energy()

        return device_info

    def _setup_daily_energy(self) -> None:
        """Setup daily energy tracking and midnight timer."""
        # Initialize daily energy values
        self._daily_charge_energy = 0.0
        self._daily_discharge_energy = 0.0
        self._data_dict["daily_charge_energy"] = self._daily_charge_energy
        self._data_dict["daily_discharge_energy"] = self._daily_discharge_energy
        
        # Setup midnight timer to reset daily energy
        if self._midnight_timer is None:
            self._midnight_timer = async_track_time_change(
                self._hass, self._midnight_callback, hour=0, minute=0, second=0
            )

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

        # Sign power based on current direction
        if "total_power" in self._data_dict:
            power = abs(self._data_dict["total_power"])
            if self._data_dict.get("total_current", 0) < 0:
                power = -power
            if self._data_dict["total_power"] != power:
                self._data_dict["total_power"] = power
                if "total_power" in self._entities:
                    changed_entities.add("total_power")

        # Update daily energy calculations
        self._update_daily_energy()

        for name in changed_entities:
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()

        # Update daily energy entities if they exist
        if "daily_charge_energy" in self._entities:
            self._entities["daily_charge_energy"].schedule_update_ha_state()
        if "daily_discharge_energy" in self._entities:
            self._entities["daily_discharge_energy"].schedule_update_ha_state()

        self._reset_notify_clear_timer()

    def _update_daily_energy(self) -> None:
        """Update daily charge and discharge energy based on power consumption."""
        current_time = datetime.now()
        current_power = self._data_dict.get("total_power", 0.0) / 1000.0 # Power in watts
        
        if self._last_update_time is not None and self._last_power is not None:
            # Calculate time difference in hours
            time_diff = (current_time - self._last_update_time).total_seconds() / 3600.0
            
            # Use average power for energy calculation (trapezoidal integration)
            avg_power = (current_power + self._last_power) / 2.0
            
            # Calculate energy in kWh
            energy_kwh = abs(avg_power) * time_diff / 1000.0
            
            # Add to appropriate daily total based on power direction
            if avg_power > 0:  # Charging (positive power)
                self._daily_charge_energy += energy_kwh
            elif avg_power < 0:  # Discharging (negative power)
                self._daily_discharge_energy += energy_kwh
        
        # Update data dictionary
        self._data_dict["daily_charge_energy"] = self._daily_charge_energy
        self._data_dict["daily_discharge_energy"] = self._daily_discharge_energy
        
        # Store current values for next calculation
        self._last_update_time = current_time
        self._last_power = current_power

    async def _midnight_callback(self, now) -> None:
        """Midnight callback to reset daily energy counters."""
        self._daily_charge_energy = 0.0
        self._daily_discharge_energy = 0.0
        self._data_dict["daily_charge_energy"] = self._daily_charge_energy
        self._data_dict["daily_discharge_energy"] = self._daily_discharge_energy
        
        # Update entity states
        if "daily_charge_energy" in self._entities:
            self._entities["daily_charge_energy"].schedule_update_ha_state()
        if "daily_discharge_energy" in self._entities:
            self._entities["daily_discharge_energy"].schedule_update_ha_state()

    async def handle_cmd(self, cmd: int, value: Any) -> None:
        """Handle writes."""
        if isinstance(value, (int, float)):
            info = self.parser.protocol_data.get("registers", {}).get(cmd, {})
            scale = info.get("scale", 1.0)
            write_command = info.get("write_command", 16)
            if info.get("type") in ("UINT32", "INT32"):
                value = int(value)
                value_high = (value >> 16) & 0xFFFF
                value_low = value & 0xFFFF
                value_list = [value_high, value_low]
            else:
                value_list = [int(value)]
            data = self.parser.pack_data(self.slave_id, cmd, value_list, write_command)
            await self.mqtt_manager.publish(self.cmd_topic, data)
