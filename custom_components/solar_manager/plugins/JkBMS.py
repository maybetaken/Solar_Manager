"""JkBms device class for Solar Manager integration.

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
from datetime import datetime, date, time, timedelta
from typing import Any
import asyncio

from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)

# RTC tick counter (0x1200 block + 0x100): seconds since the device epoch.
RTC_TICKS_REGISTER = 0x301300
RTC_EPOCH = datetime(2020, 1, 1)
# Time calibration command (0x1600 block + 0x12, "对时 Timecalibration", UINT32).
# The payload uses the same basis as RTCTicks: seconds since 2020-01-01.
RTC_CALIBRATION_REGISTER = 0x301612

# Cell existence bitmap ("BIT[n]为1表示该电池存在"): tells how many cells the
# pack currently has. DIY packs get rebuilt with different cell counts, so the
# 32 fixed cell-voltage entities are enabled/disabled in the entity registry
# to match.
CELL_EXIST_MASK_REGISTER = 0x301240
CELL_ENTITY_PREFIX = "cell_voltage_"


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
        self._active_cell_count = None
        self._hidden_cell_entities: set[str] = set()
        
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

        # Diagnostic-only action: push the current system time into the BMS RTC
        device_info["button"].append(
            {
                "name": "sync_rtc_time",
                "diagnostic": True,
                "icon": "mdi:clock-check-outline",
            }
        )

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

        # Render the RTC tick counter as the device's current clock so the
        # drift against real time is visible.
        rtc_ticks = parsed_data.pop(RTC_TICKS_REGISTER, None)
        if rtc_ticks is not None:
            name = self._register_to_name.get(RTC_TICKS_REGISTER)
            if name and isinstance(rtc_ticks, (int, float)):
                device_time = RTC_EPOCH + timedelta(seconds=int(rtc_ticks))
                value = device_time.strftime("%Y-%m-%d %H:%M:%S")
                if self._data_dict.get(name) != value:
                    self._data_dict[name] = value
                    if name in self._entities:
                        changed_entities.add(name)

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

        # Match the cell-voltage entities to the cells the pack reports
        mask = self._data_dict.get("cell_exist_mask")
        if isinstance(mask, (int, float)) and int(mask) > 0:
            self._apply_cell_exist_mask(int(mask))

        for name in changed_entities:
            entity = self._entities.get(name)
            if entity is None or name in self._hidden_cell_entities:
                continue
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

    async def perform_action(self, action_name: str) -> None:
        """Handle device-specific actions."""
        if action_name == "sync_rtc_time":
            await self._sync_rtc_time()
            return
        await super().perform_action(action_name)

    async def _sync_rtc_time(self) -> None:
        """Push the current local time into the BMS RTC via 0x1612 (对时)."""
        now = datetime.now()
        ticks = int((now - RTC_EPOCH).total_seconds())
        value_high = (ticks >> 16) & 0xFFFF
        value_low = ticks & 0xFFFF
        data = self.parser.pack_data(
            self.slave_id,
            RTC_CALIBRATION_REGISTER,
            [value_high, value_low],
            16,
        )
        await self.mqtt_manager.publish(self.cmd_topic, data)
        _LOGGER.info(
            "Synced RTC for %s to %s (ticks %s)", self.sn, now, ticks
        )

    def _apply_cell_exist_mask(self, mask: int) -> None:
        """Enable/disable cell entities to match the cells the pack reports.

        The cell count is the highest set bit of the existence bitmap (cells
        are wired sequentially). Entities beyond it are disabled in the
        entity registry - they disappear from dashboards but the user can
        still re-enable them by hand. Entities that were not added to HA
        yet are retried on the next notify.
        """
        count = mask.bit_length()
        if count == self._active_cell_count:
            return
        if self.hass is None:
            return
        if self._sync_cell_entities(count):
            self._active_cell_count = count
            _LOGGER.debug("Cell count for %s: %s", self.sn, count)

    def _sync_cell_entities(self, count: int) -> bool:
        """Sync registry state of cell entities; return True when all synced.

        Only entities this integration disabled itself are re-enabled;
        entries the user disabled manually are left alone.
        """
        registry = er.async_get(self.hass)
        complete = True
        for name, entity in self._entities.items():
            if not name.startswith(CELL_ENTITY_PREFIX):
                continue
            try:
                index = int(name[len(CELL_ENTITY_PREFIX):])
            except ValueError:
                continue
            entry = registry.async_get(entity.entity_id) if entity.entity_id else None
            if entry is None:
                complete = False
                continue
            wanted_enabled = index < count
            if wanted_enabled and entry.disabled and entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                er.async_update_entity(self.hass, entity.entity_id, disabled_by=None)
                self._hidden_cell_entities.discard(name)
            elif not wanted_enabled and not entry.disabled:
                er.async_update_entity(
                    self.hass,
                    entity.entity_id,
                    disabled_by=er.RegistryEntryDisabler.INTEGRATION,
                )
                self._hidden_cell_entities.add(name)
        return complete

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
