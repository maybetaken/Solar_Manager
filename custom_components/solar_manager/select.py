"""Select entity for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN


class SolarManagerSelect(SelectEntity):
    """Representation of a Solar Manager select."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        register: str,
        options: list[str],
        unique_id: str,
        device_id: str,
        enum_mapping: dict[int, str],
        icon: str | None = None,
    ) -> None:
        """Initialize the select."""
        self._device = device
        self._name = name
        self._model = model
        self._register = register
        self._attr_options = options
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_icon = icon
        self._enum_mapping = enum_mapping
        self._reverse_mapping = {v: k for k, v in enum_mapping.items()}
        self._device.register_entity(name, self)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        value = self._device.get_dict(self._name)
        if value is None:
            return None
        try:
            value = int(float(value))
            return self._enum_mapping.get(value, None)
        except (ValueError, TypeError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Update the current option."""
        if option in self._attr_options:
            index = self._reverse_mapping.get(option)
            if index is not None:
                await self._device.parser.write_data(self._register, index)
                self._device._data_dict[self._name] = index
                self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the select entity is available."""
        return self.current_option is not None

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
    """Set up Solar Manager select from a config entry."""
    selects = []
    serial = entry.data[CONF_SERIAL]
    model = entry.data[CONF_MODEL]
    for item in hass.data[DOMAIN][serial].get(Platform.SELECT, []):
        unique_id = f"{item['name']}_{model}_{serial}"
        select = SolarManagerSelect(
            name=item["name"],
            model=model,
            device=item["device"],
            register=item["register"],
            options=item["options"],
            unique_id=unique_id,
            device_id=serial,
            enum_mapping=item["enum_mapping"],
            icon=item.get("icon"),
        )
        selects.append(select)
    async_add_entities(selects)
