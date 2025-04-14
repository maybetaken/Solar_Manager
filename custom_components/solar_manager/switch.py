"""Switch entity for Solar Manager integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
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
        self._attr_translation_key = name
        self._attr_has_entity_name = True
        self._attr_icon = icon

        self._parser.set_update_callback(self._register, self.on_data_update)

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
            "identifiers": {(DOMAIN, self._device_id)},
            "name": f"Solar Manager {self._device_id}",
            "manufacturer": "Solar Manager Inc.",
            "model": "Modbus Device",
            "sw_version": "1.0",
        }


class SolarManagerDiagnosticSwitch(SwitchEntity):
    """Representation of a Solar Manager diagnostic switch."""

    def __init__(
        self,
        name: str,
        device: Any,
        unique_id: str,
        device_id: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the diagnostic switch."""
        self._device = device
        self._attr_unique_id = unique_id
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._device_id = device_id
        self._attr_translation_key = name.lower()
        self._attr_has_entity_name = True

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
        unique_id = f"{item['name']}_{entry.data[CONF_MODEL]}_{serial}"
        if item.get("diagnostic"):
            switch = SolarManagerDiagnosticSwitch(
                name=item["name"],
                device=item["device"],
                unique_id=unique_id,
                device_id=serial,
                icon=item.get("icon"),
            )
            # Register the diagnostic switch with the device
            item["device"].register_diagnostic_entity(item["name"], switch)
        else:
            switch = SolarManagerSwitch(
                name=item["name"],
                parser=item["parser"],
                register=item["register"],
                unique_id=unique_id,
                device_id=serial,
                icon=item.get("icon"),
            )
        switches.append(switch)
    async_add_entities(switches)
