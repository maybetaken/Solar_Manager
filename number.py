"""Number entity for Solar Manager integration."""

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SERIAL, DOMAIN
from .protocol_helper.modbus_protocol_helper import ProtocolHelper


class SolarManagerNumber(NumberEntity):
    """Representation of a Solar Manager number."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
    ) -> None:
        """Initialize the number."""
        self._attr_name = name
        self._parser = parser
        self._register = register
        self._attr_value = None
        self._attr_unique_id = unique_id
        self._device_id = device_id

    async def async_update(self) -> None:
        """Fetch new state data for the number."""
        data = await self._parser.read_data(self._register)
        self._attr_value = data

    async def async_set_value(self, value: float) -> None:
        """Update the current value."""
        await self._parser.write_data(self._register, value)

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
    """Set up Solar Manager number from a config entry."""
    numbers = []
    serial = entry.data[CONF_SERIAL]
    for item in hass.data[DOMAIN][serial].get(Platform.NUMBER, []):
        unique_id = f"{entry.entry_id}-{serial}-{item['register']}"
        number = SolarManagerNumber(
            item["name"], item["parser"], item["register"], unique_id, serial
        )
        numbers.append(number)
    async_add_entities(numbers)
