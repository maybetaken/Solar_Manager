"""Button entity for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN


class SolarManagerActionButton(ButtonEntity):
    """Representation of a Solar Manager action button."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the action button."""
        self._device = device
        self._model = model
        self._attr_unique_id = unique_id
        self._attr_icon = icon
        self._device_id = device_id
        self._attr_translation_key = name.lower()
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._action_name = name

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._device.perform_action(self._action_name)

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": f"{self._model} {self._device_id}",
            "manufacturer": "@maybetaken",
            "model": self._model,
            "sw_version": "1.0",
        }


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Solar Manager action buttons from a config entry."""
    entities = []
    serial = entry.data[CONF_SERIAL]
    model = entry.data[CONF_MODEL]

    for device in hass.data[DOMAIN][serial].get(Platform.BUTTON, []):
        unique_id = f"{device['name']}_action_{model}_{serial}"
        button = SolarManagerActionButton(
            name=device["name"],
            model=model,
            device=device["device"],
            unique_id=unique_id,
            device_id=serial,
            icon=device.get("icon"),
        )
        entities.append(button)

    async_add_entities(entities)
