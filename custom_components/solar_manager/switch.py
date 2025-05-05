"""Switch entity for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN


class SolarManagerSwitch(SwitchEntity):
    """Representation of a Solar Manager switch."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        register: str,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the switch."""
        self._device = device
        self._name = name
        self._model = model
        self._register = register
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_icon = icon
        self._device.register_entity(name, self)

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        value = self._device.get_dict(self._name)
        if value is None:
            return None
        try:
            return bool(int(float(value)))
        except (ValueError, TypeError):
            return None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._device.parser.write_data(self._register, 1)
        self._device._data_dict[self._name] = 1
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._device.parser.write_data(self._register, 0)
        self._device._data_dict[self._name] = 0
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        return self._device.get_dict(self._name) is not None

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


class SolarManagerDiagnosticSwitch(SwitchEntity):
    """Representation of a Solar Manager diagnostic switch."""

    def __init__(
        self,
        name: str,
        model: str,
        device: Any,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the diagnostic switch."""
        self._device = device
        self._model = model
        self._attr_unique_id = unique_id
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._device_id = device_id
        self._attr_translation_key = name.lower()
        self._attr_has_entity_name = True
        self._device.register_diagnostic_entity(name, self)

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        diagnostics = self._device.get_diagnostics()
        return bool(diagnostics.get("led"))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._device.set_led(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._device.set_led(False)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        return self._device.get_diagnostics().get("led") is not None

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
    """Set up Solar Manager switch from a config entry."""
    switches = []
    serial = entry.data[CONF_SERIAL]
    model = entry.data[CONF_MODEL]
    for item in hass.data[DOMAIN][serial].get(Platform.SWITCH, []):
        unique_id = f"{item['name']}_{model}_{serial}"
        if item.get("diagnostic"):
            switch = SolarManagerDiagnosticSwitch(
                name=item["name"],
                model=model,
                device=item["device"],
                unique_id=unique_id,
                device_id=serial,
                icon=item.get("icon"),
            )
        else:
            switch = SolarManagerSwitch(
                name=item["name"],
                model=model,
                device=item["device"],
                register=item["register"],
                unique_id=unique_id,
                device_id=serial,
                icon=item.get("icon"),
            )
        switches.append(switch)
    async_add_entities(switches)
