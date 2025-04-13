"""Sensor entity for Solar Manager integration."""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .protocol_helper.protocol_helper import ProtocolHelper

unit_mapping = {
    "AMPERE": UnitOfElectricCurrent.AMPERE,
    "PERCENTAGE": PERCENTAGE,
    "VOLT": UnitOfElectricPotential.VOLT,
    "WATT": UnitOfPower.WATT,
    "KILOWATT_HOUR": UnitOfEnergy.KILO_WATT_HOUR,
    "WATT_HOUR": UnitOfEnergy.WATT_HOUR,
    "CELSIUS": UnitOfTemperature.CELSIUS,
    "HERTZ": "Hz",
    "AMPERE_HOUR": "Ah",
    None: None,
}


class SolarManagerSensor(SensorEntity):
    """Representation of a Solar Manager sensor."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
        unit: str | None = None,
        scale_factor: float = 1.0,
        display_precision: int = 0,
        icon: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._parser = parser
        self._register = register
        self._attr_state = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_native_unit_of_measurement = unit_mapping.get(unit)
        self._attr_suggested_display_precision = display_precision
        self._attr_icon = icon
        self._scale_factor = scale_factor

        self._parser.set_update_callback(self._register, self.on_data_update)

    async def on_data_update(self, value: Any) -> None:
        """Set current option based on data update."""
        try:
            value = float(value) * self._scale_factor
            if self._attr_suggested_display_precision == 0:
                value = int(value)
            self._attr_native_value = value
        except (ValueError, TypeError):
            self._attr_native_value = None
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        return self._attr_native_value is not None

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},  # Ensure same device
            "name": f"Solar Manager {self._device_id}",
            "manufacturer": "Solar Manager Inc.",
            "model": "Modbus Device",
            "sw_version": "1.0",
        }


class SolarManagerEnumSensor(SolarManagerSensor):
    """Representation of a Solar Manager sensor with enum mapping."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
        enum_mapping: dict[int, str],
        unit: str | None = None,
        scale_factor: float = 1.0,
        display_precision: int = 0,
        icon: str | None = None,
    ) -> None:
        """Initialize the enum sensor."""
        super().__init__(
            name,
            parser,
            register,
            unique_id,
            device_id,
            unit,
            scale_factor,
            display_precision,
            icon,
        )
        self._attr_suggested_display_precision = None
        self._enum_mapping = enum_mapping

    async def on_data_update(self, value: Any) -> None:
        """Set current option based on data update."""
        self.schedule_update_ha_state()
        try:
            value = float(value) * self._scale_factor
            # Convert value to int and map to string
            self._attr_native_value = self._enum_mapping.get(
                int(value), f"Unknown ({value})"
            )
        except (ValueError, TypeError):
            # Handle invalid values gracefully
            self._attr_native_value = None
        self.schedule_update_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Solar Manager sensor from a config entry."""
    sensors = []
    serial = entry.data[CONF_SERIAL]
    model = entry.data[CONF_MODEL]
    for device in hass.data[DOMAIN][serial].get(Platform.SENSOR, []):
        unit = device.get("unit", None)
        unique_id = f"{device['name']}_{model}_{serial}"
        if "enum_mapping" in device:
            # Use SolarManagerEnumSensor if enum_mapping is provided
            sensor = SolarManagerEnumSensor(
                device["name"],
                device["parser"],
                device["register"],
                unique_id,
                serial,
                device["enum_mapping"],
                unit,
                device.get("scale", 1.0),
                device.get("display_precision", 0),
                device.get("icon"),
            )
        else:
            # Use regular SolarManagerSensor
            sensor = SolarManagerSensor(
                device["name"],
                device["parser"],
                device["register"],
                unique_id,
                serial,
                unit,
                device.get("scale", 1.0),
                device.get("display_precision", 0),
                device.get("icon"),
            )
        sensors.append(sensor)
    async_add_entities(sensors)
