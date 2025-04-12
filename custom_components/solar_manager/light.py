"""Light entity for Solar Manager integration."""

from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .protocol_helper.protocol_helper import ProtocolHelper


class SolarManagerLight(LightEntity):
    """Representation of a Solar Manager light."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
    ) -> None:
        """Initialize the light."""
        self._attr_name = name
        self._parser = parser
        self._register = register
        self._attr_is_on = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._parser.set_update_callback(self._register, self.on_data_update)

    async def on_data_update(self, value: Any) -> None:
        """Set light value based on data update."""
        if isinstance(value, str):
            self._attr_is_on = value == "on"
        else:
            self._attr_is_on = None
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        await self._parser.write_data(self._register, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self._parser.write_data(self._register, "off")
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the light entity is available."""
        return self._attr_is_on is not None

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
    """Set up Solar Manager light from a config entry."""
    lights = []
    serial = entry.data[CONF_SERIAL]
    model = entry.data[CONF_MODEL]
    for item in hass.data[DOMAIN][serial].get(Platform.LIGHT, []):
        unique_id = f"{item['name']}_{model}_{serial}"
        light = SolarManagerLight(
            item["name"], item["parser"], item["register"], unique_id, serial
        )
        lights.append(light)
    async_add_entities(lights)
