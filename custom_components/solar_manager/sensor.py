"""Sensor entity for Solar Manager integration."""

from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
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
from .protocol_helper.protocol_helper import ProtocolHelper

SENSOR_STYLES: Final[dict[str, SensorEntityDescription]] = {
    "direction": SensorEntityDescription(
        key="direction",
    ),
    "voltage": SensorEntityDescription(
        key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
        suggested_display_precision=1,
    ),
    "battery": SensorEntityDescription(
        key="battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
    ),
    "temperature": SensorEntityDescription(
        key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
    ),
    "current": SensorEntityDescription(
        key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CURRENT,
    ),
    "power": SensorEntityDescription(
        key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=1,
    ),
    "energy": SensorEntityDescription(
        key="energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=1,
    ),
    "runtime": SensorEntityDescription(
        key="runtime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DURATION,
    ),
}

DEFAULT_SENSOR_STYLE = SensorEntityDescription(
    key="default",
    state_class=SensorStateClass.MEASUREMENT,
)

ENTITY_CATEGORIES: Final[dict[str, EntityCategory]] = {
    "diagnostic": EntityCategory.DIAGNOSTIC,
    "config": EntityCategory.CONFIG,
    "setting": EntityCategory.CONFIG,
    "rssi": EntityCategory.DIAGNOSTIC,
    "link": EntityCategory.DIAGNOSTIC,
    "delta": EntityCategory.DIAGNOSTIC,
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
    ) -> None:
        """Initialize the sensor."""
        self._parser = parser
        self._register = register
        self._attr_state = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True

        name_lower = name.lower()
        self.entity_description = next(
            (
                style
                for keyword, style in SENSOR_STYLES.items()
                if keyword in name_lower
            ),
            DEFAULT_SENSOR_STYLE,
        )

        self._attr_entity_category = None
        for keyword, category in ENTITY_CATEGORIES.items():
            if keyword in name_lower:
                self._attr_entity_category = category
                break

        self._parser.set_update_callback(self._register, self.on_data_update)

    async def on_data_update(self, value: Any) -> None:
        """Set current option based on data update."""
        self._attr_native_value = value
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
    ) -> None:
        """Initialize the enum sensor."""
        super().__init__(name, parser, register, unique_id, device_id)
        self._enum_mapping = enum_mapping

        # Create a new entity description without numeric-related attributes
        self.entity_description = SensorEntityDescription(
            key=name.lower(),
            translation_key=name.lower(),
        )

    async def on_data_update(self, value: Any) -> None:
        """Set current option based on data update."""
        try:
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
            )
        else:
            # Use regular SolarManagerSensor
            sensor = SolarManagerSensor(
                device["name"],
                device["parser"],
                device["register"],
                unique_id,
                serial,
            )
        sensors.append(sensor)
    async_add_entities(sensors)
