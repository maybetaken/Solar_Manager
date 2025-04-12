"""Number entity for Solar Manager integration."""

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .protocol_helper.protocol_helper import ProtocolHelper


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
        self._attr_mode = "box"
        self._parser = parser
        self._register = register
        self._attr_native_value = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._parser.set_update_callback(self._register, self.on_data_update)

    async def on_data_update(self, value: Any) -> None:
        """Set number value based on data update."""
        if isinstance(value, (int, float)):
            self._attr_native_value = float(value)
        else:
            self._attr_native_value = None
        self.schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._parser.write_data(self._register, value)

    @property
    def available(self) -> bool:
        """Return if the number entity is available."""
        return self._attr_native_value is not None

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
    model = entry.data[CONF_MODEL]
    for item in hass.data[DOMAIN][serial].get(Platform.NUMBER, []):
        unique_id = f"{item['name']}_{model}_{serial}"
        number = SolarManagerNumber(
            item["name"], item["parser"], item["register"], unique_id, serial
        )
        numbers.append(number)
    async_add_entities(numbers)
