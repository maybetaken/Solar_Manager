"""Light entity for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN


class SolarManagerLight(LightEntity):
    """Representation of a Solar Manager light."""

    def __init__(
        self,
        name: str,
        device: Any,
        register: str,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the light."""
        self._device = device
        self._name = name
        self._register = register
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_icon = icon
        self._device.register_entity(name, self)

    @property
    def is_on(self) -> bool | None:
        """Return true if the light is on."""
        value = self._device.get_dict(self._name)
        if value is None:
            return None
        return value == "on"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        await self._device.parser.write_data(self._register, "on")
        self._device._data_dict[self._name] = "on"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self._device.parser.write_data(self._register, "off")
        self._device._data_dict[self._name] = "off"
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the light entity is available."""
        return self._device.get_dict(self._name) is not None

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
    """Set up Solar Manager light from a config entry."""
    lights = []
    serial = entry.data[CONF_SERIAL]
    for item in hass.data[DOMAIN][serial].get(Platform.LIGHT, []):
        unique_id = f"{item['name']}_{entry.data[CONF_MODEL]}_{serial}"
        light = SolarManagerLight(
            name=item["name"],
            device=item["device"],
            register=item["register"],
            unique_id=unique_id,
            device_id=serial,
            icon=item.get("icon"),
        )
        lights.append(light)
    async_add_entities(lights)
