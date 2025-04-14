"""Number entity for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .protocol_helper.protocol_helper import ProtocolHelper

unit_mapping = {
    "AMPERE": UnitOfElectricCurrent.AMPERE,
    "PERCENTAGE": PERCENTAGE,
    "VOLT": UnitOfElectricPotential.VOLT,
    "WATT": UnitOfPower.WATT,
    "KILOWATT_HOUR": UnitOfEnergy.KILO_WATT_HOUR,
    "CELSIUS": UnitOfTemperature.CELSIUS,
    "AMPERE_HOUR": "Ah",  # No direct HA constant; use None for custom unit
    None: None,  # Handle null units (e.g., communication_address)
}


class SolarManagerNumber(NumberEntity):
    """Representation of a Solar Manager number."""

    def __init__(
        self,
        name: str,
        parser: ProtocolHelper,
        register: str,
        unique_id: str,
        device_id: str,
        min_value: float,
        max_value: float,
        unit: str | None = None,
        step: float = 1.0,
        scale_factor: float = 1.0,
        display_precision: int = 0,
        icon: str | None = None,
    ) -> None:
        """Initialize the number."""
        self._attr_mode = "box"
        self._parser = parser
        self._register = register  # Convert 0x0B to 11
        self._attr_native_value = None
        self._attr_unique_id = unique_id
        self._device_id = device_id
        self._attr_translation_key = name.lower()
        self._attr_has_entity_name = True
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_unit_of_measurement = unit
        self._attr_native_step = step
        self._attr_suggested_display_precision = display_precision
        self._attr_icon = icon
        self._scale_factor = scale_factor
        self._parser.set_update_callback(self._register, self.on_data_update)

    async def on_data_update(self, value: Any) -> None:
        """Set number value based on data update."""
        try:
            value = float(value) * self._scale_factor
            if self._attr_native_min_value <= value <= self._attr_native_max_value:
                if self._attr_suggested_display_precision == 0:
                    value = int(value)
                self._attr_native_value = value
            else:
                self._attr_native_value = None
        except (ValueError, TypeError):
            self._attr_native_value = None
        self.schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        register_value = int(value / self._scale_factor)
        await self._parser.write_data(self._register, register_value)
        if self._attr_suggested_display_precision == 0:
            value = int(value)
        self._attr_native_value = value
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if the number entity is available."""
        return self._attr_native_value is not None

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": f"Solar Manager {self._device_id}",
            "manufacturer": "@maybetaken",
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
        unit = item.get("unit")
        unique_id = f"{item['name']}_{entry.data[CONF_MODEL]}_{serial}"
        number = SolarManagerNumber(
            name=item["name"],
            parser=item["parser"],
            register=item["register"],
            unique_id=unique_id,
            device_id=serial,
            min_value=item.get("min_value", 0.0),
            max_value=item.get("max_value", 100.0),
            unit=unit_mapping.get(unit),
            step=item.get("step", 1.0),
            scale_factor=item.get("scale", 1.0),
            display_precision=item.get("display_precision", 0),
            icon=item.get("icon"),
        )
        numbers.append(number)
    async_add_entities(numbers)
