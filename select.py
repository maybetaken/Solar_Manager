"""Select entity for Solar Manager integration."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN
from .protocol_helper.modbus_protocol_helper import ProtocolHelper


class SolarManagerSelect(SelectEntity):
    """Representation of a Solar Manager select."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        options: list[str],
        unique_id: str,
        device_id: str,
    ) -> None:
        """Initialize the select."""
        self._attr_name = name
        self._parser = parser
        self._register = register
        self._attr_options = options
        self._attr_current_option = None
        self._attr_unique_id = unique_id
        self._device_id = device_id

    async def async_update(self) -> None:
        """Fetch new state data for the select."""
        data = await self._parser.read_data(self._register)
        if isinstance(data, int) and 0 <= data < len(self._attr_options):
            self._attr_current_option = self._attr_options[data]
        else:
            self._attr_current_option = None
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Update the current option."""
        if option in self._attr_options:
            index = self._attr_options.index(option)
            await self._parser.write_data(self._register, index)
            self._attr_current_option = option
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
    """Set up Solar Manager select from a config entry."""
    selects = []
    serial = entry.data[CONF_SERIAL]
    for item in hass.data[DOMAIN][serial].get(Platform.SELECT, []):
        unique_id = f"{entry.entry_id}-{serial}-{item['register']}"
        select = SolarManagerSelect(
            item["name"],
            item["parser"],
            item["register"],
            item["options"],
            unique_id,
            serial,
        )
        selects.append(select)
    async_add_entities(selects)
