"""Switch entity for Solar Manager integration."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_SERIAL
from .protocol_helper.modbus_protocol_helper import ProtocolHelper


class SolarManagerSwitch(SwitchEntity):
    """Representation of a Solar Manager switch."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
    ) -> None:
        """Initialize the switch."""
        self._attr_name = name
        self._parser = parser
        self._register = register
        self._attr_is_on = False
        self._attr_unique_id = unique_id
        self._device_id = device_id

    async def async_update(self) -> None:
        """Fetch new state data for the switch."""
        data = await self._parser.read_data(self._register)
        self._attr_is_on = data == "on"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._parser.write_data(self._register, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._parser.write_data(self._register, "off")
        self._attr_is_on = False
        self.async_write_ha_state()

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
        unique_id = f"{entry.entry_id}-{serial}-{item['register']}"
        switch = SolarManagerSwitch(
            item["name"], item["parser"], item["register"], unique_id, serial
        )
        switches.append(switch)
    async_add_entities(switches)
