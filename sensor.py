"""Sensor entity for Solar Manager integration."""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN
from .protocol_helper.protocol_helper import ProtocolHelper


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
        self._attr_name = name
        self._parser = parser
        self._register = register
        self._attr_state = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Solar Manager sensor from a config entry."""
    sensors = []
    serial = entry.data[CONF_SERIAL]
    for device in hass.data[DOMAIN][serial].get(Platform.SENSOR, []):
        unique_id = f"{entry.entry_id}-{serial}-{device['register']}"
        sensor = SolarManagerSensor(
            device["name"], device["parser"], device["register"], unique_id, serial
        )
        sensors.append(sensor)
    async_add_entities(sensors)
