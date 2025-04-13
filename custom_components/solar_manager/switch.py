"""Switch entity for Solar Manager integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN
from .protocol_helper.protocol_helper import ProtocolHelper


class SolarManagerSwitch(SwitchEntity):
    """Representation of a Solar Manager switch."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the switch."""
        self._parser = parser
        self._register = register
        self._attr_is_on = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._parser.set_update_callback(self._register, self.on_data_update)
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_icon = icon

    async def on_data_update(self, value: Any) -> None:
        """Set switch value based on data update."""
        if isinstance(value, int):
            self._attr_is_on = value
        else:
            self._attr_is_on = None
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._parser.write_data(self._register, 1)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._parser.write_data(self._register, 0)
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
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
    """Set up Solar Manager switch from a config entry."""
    switches = []
    serial = entry.data[CONF_SERIAL]
    for item in hass.data[DOMAIN][serial].get(Platform.SWITCH, []):
        unique_id = f"{item['name']}_{item['model']}_{serial}"
        switch = SolarManagerSwitch(
            item["name"],
            item["parser"],
            item["register"],
            unique_id,
            serial,
            item.get("icon"),
        )
        switches.append(switch)
    async_add_entities(switches)
