"""Sensor entity for Solar Manager integration.

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

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .entity import BaseEntity

unit_mapping = {
    "AMPERE": UnitOfElectricCurrent.AMPERE,
    "PERCENTAGE": PERCENTAGE,
    "VOLT": UnitOfElectricPotential.VOLT,
    "WATT": UnitOfPower.WATT,
    "KILO_WATT": UnitOfPower.KILO_WATT,
    "KILOWATT_HOUR": UnitOfEnergy.KILO_WATT_HOUR,
    "WATT_HOUR": UnitOfEnergy.WATT_HOUR,
    "CELSIUS": UnitOfTemperature.CELSIUS,
    "SECONDS": UnitOfTime.SECONDS,
    "HERTZ": "Hz",
    "AMPERE_HOUR": "Ah",
    None: None,
}

device_class_mapping = {
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "frequency": SensorDeviceClass.FREQUENCY,
    "power_factor": SensorDeviceClass.POWER_FACTOR,
    "battery": SensorDeviceClass.BATTERY,
    "timestamp": SensorDeviceClass.TIMESTAMP,
    "enum": None,
    "switch": None,
    "None": None,
}

state_class_mapping = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total": SensorStateClass.TOTAL,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
    "None": None,
}

_DURATION_UNITS = (
    (365 * 86400, "y"),
    (30 * 86400, "m"),
    (86400, "d"),
    (3600, "h"),
    (60, "m"),
    (1, "s"),
)


def format_duration(seconds: float | None) -> str | None:
    """Format seconds as a compact duration like 1y2m3d4h5m6s.

    Leading zero units are dropped (0y0m3d0h5m0s -> 3d0h5m0s); month and
    minute both use "m", disambiguated by position. Everything below one
    second reads 0s.
    """
    if seconds is None:
        return None
    try:
        total = int(seconds)
    except (ValueError, TypeError, OverflowError):
        return None
    if total <= 0:
        return "0s"

    parts = []
    for step, suffix in _DURATION_UNITS:
        value, total = divmod(total, step)
        parts.append((value, suffix))

    while len(parts) > 1 and parts[0][0] == 0:
        parts.pop(0)
    return "".join(f"{value}{suffix}" for value, suffix in parts)


class SolarManagerSensor(BaseEntity, SensorEntity):
    """Representation of a Solar Manager sensor."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        unique_id: str,
        device_id: str,
        unit: str | None = None,
        scale_factor: float = 1.0,
        display_precision: int | None = None,
        icon: str | None = None,
        offset: int = 0,
        device_class: str | None = None,
        state_class: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._device = device
        self._name = name
        self._model = model
        self._attr_unique_id = unique_id
        self._offset = offset
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_native_unit_of_measurement = unit_mapping.get(unit, unit)
        self._attr_suggested_display_precision = display_precision
        self._attr_icon = icon
        self._scale_factor = scale_factor
        self._attr_device_class = device_class_mapping.get(device_class)
        self._attr_state_class = state_class_mapping.get(state_class)
        self._device.register_entity(name, self)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self._device.get_dict(self._name)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            value = round(float(value - self._offset) * self._scale_factor, 3)
            if self._attr_suggested_display_precision == 0:
                value = int(value)
        except (ValueError, TypeError):
            return None
        return value

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        return self.native_value is not None


class SolarManagerDurationSensor(SolarManagerSensor):
    """Sensor rendering a seconds value as a duration like 1y2m3d4h5s."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        unique_id: str,
        device_id: str,
        scale_factor: float = 1.0,
        icon: str | None = None,
        offset: int = 0,
    ) -> None:
        """Initialize the duration sensor (no unit, it is baked into the value)."""
        super().__init__(
            name,
            model,
            device,
            unique_id,
            device_id,
            unit=None,
            scale_factor=scale_factor,
            display_precision=None,
            icon=icon,
            offset=offset,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self._device.get_dict(self._name)
        if value is None:
            return None
        try:
            seconds = (float(value) - self._offset) * self._scale_factor
        except (ValueError, TypeError):
            return None
        return format_duration(seconds)


class SolarManagerEnumSensor(SolarManagerSensor):
    """Representation of a Solar Manager sensor with enum mapping."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        unique_id: str,
        device_id: str,
        enum_mapping: dict[int, str],
        unit: str | None = None,
        scale_factor: float = 1.0,
        icon: str | None = None,
    ) -> None:
        """Initialize the enum sensor."""
        super().__init__(
            name,
            model,
            device,
            unique_id,
            device_id,
            unit,
            scale_factor,
            0,
            icon,
        )
        self._attr_suggested_display_precision = None
        self._enum_mapping = enum_mapping

    @property
    def native_value(self):
        """Return the state of the sensor."""
        value = self._device.get_dict(self._name)
        if value is None:
            return None
        try:
            value = round(float(value) * self._scale_factor, 3)
            return self._enum_mapping.get(int(value), f"Unknown ({value})")
        except (ValueError, TypeError):
            return None


class SolarManagerDiagnosticSensor(BaseEntity, SensorEntity):
    """Representation of a Solar Manager diagnostic sensor."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        unique_id: str,
        device_id: str,
        unit: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize the diagnostic sensor."""
        self._device = device
        self._model = model
        self._sensor_name = name.lower()
        self._attr_unique_id = unique_id
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = unit
        self._device_id = device_id
        self._attr_translation_key = name.lower()
        self._attr_has_entity_name = True

        if self._sensor_name == "rssi":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._device.register_diagnostic_entity(name, self)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        diagnostics = self._device.get_diagnostics()
        return diagnostics.get(self._sensor_name)

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        return self.native_value is not None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Solar Manager sensor from a config entry."""
    sensors = []
    serial = entry.data[CONF_SERIAL]
    model = entry.data[CONF_MODEL]
    for device in hass.data[DOMAIN][serial].get(Platform.SENSOR, []):
        unique_id = f"{device['name']}_{model}_{serial}"
        if device.get("diagnostic"):
            sensor = SolarManagerDiagnosticSensor(
                name=device["name"],
                model=model,
                device=device["device"],
                unique_id=unique_id,
                device_id=serial,
                unit=device.get("unit"),
                icon=device.get("icon"),
            )
        elif device.get("unit") == "DURATION":
            sensor = SolarManagerDurationSensor(
                name=device["name"],
                model=model,
                device=device["device"],
                unique_id=unique_id,
                device_id=serial,
                scale_factor=device.get("scale", 1.0),
                icon=device.get("icon"),
                offset=device.get("offset", 0),
            )
        elif "enum_mapping" in device:
            sensor = SolarManagerEnumSensor(
                name=device["name"],
                model=model,
                device=device["device"],
                unique_id=unique_id,
                device_id=serial,
                enum_mapping=device["enum_mapping"],
                unit=device.get("unit"),
                scale_factor=device.get("scale", 1.0),
                icon=device.get("icon"),
            )
        else:
            sensor = SolarManagerSensor(
                name=device["name"],
                model=model,
                device=device["device"],
                unique_id=unique_id,
                device_id=serial,
                unit=device.get("unit"),
                scale_factor=device.get("scale", 1.0),
                display_precision=device.get("display_precision", 0),
                icon=device.get("icon"),
                offset=device.get("offset", 0),
                device_class=device.get("device_class", None),
                state_class=device.get("state_class", None),
            )
        sensors.append(sensor)
    async_add_entities(sensors)
