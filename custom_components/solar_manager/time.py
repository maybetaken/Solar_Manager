"""Time entity for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import _LOGGER, CONF_MODEL, CONF_SERIAL, DOMAIN


class SolarManagerTime(TimeEntity):
    """Representation of a Solar Manager time entity (e.g., scheduled times)."""

    def __init__(
        self,
        name: str,
        device: Any,
        register: str,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the time entity."""
        if not name or not isinstance(name, str) or not name.strip():
            _LOGGER.error("Invalid entity name provided: %s", name)
            raise ValueError(f"Invalid entity name: {name}")
        self._device = device
        self._name = name
        self._register = register
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_icon = icon
        self._device.register_entity(name, self)
        _LOGGER.debug("Created time entity: name=%s, unique_id=%s", name, unique_id)

    @property
    def native_value(self):
        """Return the state of the time entity."""
        value = self._device.get_dict(self._name)
        _LOGGER.debug("Native value for %s: %s", self._name, value)
        if value is None:
            return None
        try:
            time_str = value.get("time")
            if not time_str:
                _LOGGER.debug("No time set for %s, marking unavailable", self._name)
                return None
            time_obj = dt_util.parse_time(time_str)
            if time_obj is None:
                _LOGGER.warning("Invalid time for %s: %s", self._name, time_str)
                return None
            return time_obj
        except (ValueError, TypeError, AttributeError) as e:
            _LOGGER.error(
                "Failed to parse time for %s: %s, value=%s", self._name, e, value
            )
            return None

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        value = self._device.get_dict(self._name)
        if value and isinstance(value, dict):
            return {"interval_days": value.get("interval_days", 0)}
        return {}

    async def async_set_value(self, value):
        """Set a new time value."""
        try:
            hour = value.hour
            minute = value.minute
            # Send hour and minute as a combined value (no interval_days packing)
            packed_value = (hour << 8) | minute
            await self._device.parser.write_data(self._register, packed_value)
            self.async_write_ha_state()
        except ValueError as e:
            _LOGGER.error("Invalid time value for %s: %s", self._name, e)

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        value = self._device.get_dict(self._name)
        if value is None:
            _LOGGER.debug("Entity %s unavailable: value is None", self._name)
            return False
        time_str = value.get("time")
        valid = bool(time_str)
        if not valid:
            _LOGGER.debug("Entity %s unavailable: no time set", self._name)
        return valid

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": f"Solar Manager {self._device_id}",
            "manufacturer": "Solar Manager Inc.",
            "model": "Modbus Device",
            "sw_version": "1.0",
        }


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Solar Manager time entities from a config entry."""
    entities = []
    serial = entry.data[CONF_SERIAL]
    time_items = hass.data[DOMAIN][serial].get(Platform.TIME, [])
    _LOGGER.debug("Time items for serial %s: %s", serial, time_items)
    for item in time_items:
        name = item.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            _LOGGER.error("Skipping entity with invalid name: %s, item=%s", name, item)
            continue
        unique_id = f"{name}_{entry.data[CONF_MODEL]}_{serial}"
        entity = SolarManagerTime(
            name=name,
            device=item["device"],
            register=item.get("register"),
            unique_id=unique_id,
            device_id=serial,
            icon=item.get("icon"),
        )
        entities.append(entity)
        _LOGGER.debug(
            "Added time entity: name=%s, register=%s", name, item.get("register")
        )
    async_add_entities(entities)
