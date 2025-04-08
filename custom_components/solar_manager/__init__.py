"""The Solar Manager integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import _LOGGER, CONF_MODEL, CONF_SERIAL, DOMAIN
from .device_protocol.protocol_map import protocol_map
from .mqtt_helper.mqtt_global import get_mqtt_manager
from .plugins.base_device import BaseDevice
from .plugins.MakeSkyBlue import MakeSkyBlueDevice

# List the platforms that you want to support.
_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]

# Mapping of model names to device classes
device_class_map: dict[str, type[BaseDevice]] = {
    "MakeSkyBlue": MakeSkyBlueDevice,
    # Add other device classes here
}

# Create ConfigEntry type alias with API object
type SolarManagerConfigEntry = ConfigEntry  # Update with actual API type if available

mqtt_manager = get_mqtt_manager()


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarManagerConfigEntry
) -> bool:
    """Set up Solar Manager from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    # Handle the protocol and device setup
    model = entry.data[CONF_MODEL]
    serial = entry.data[CONF_SERIAL]
    protocol = protocol_map.get(model)
    if protocol is None:
        return False

    device_class = device_class_map.get(model)
    if device_class is None:
        return False

    protocol_file_path = Path(__file__).parent / "device_protocol" / f"{protocol}.json"
    device = device_class(hass, protocol_file_path, serial, model)
    await device.load_protocol()  # Ensure protocol data is loaded asynchronously
    solar_platforms = device.unpack_device_info()
    if serial not in hass.data[DOMAIN]:
        hass.data[DOMAIN][serial] = {}
        hass.data[DOMAIN][serial]["devices"] = device
    for platform, items in solar_platforms.items():
        for item in items:
            item_name = f"{item['name']}_{model}_{serial}"
            item["name"] = item_name
            item["parser"] = device.parser
            if platform not in hass.data[DOMAIN][serial]:
                hass.data[DOMAIN][serial][platform] = []
            hass.data[DOMAIN][serial][platform].append(item)
        await hass.config_entries.async_forward_entry_setups(entry, [platform])

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SolarManagerConfigEntry
) -> bool:
    """Unload a config entry."""
    serial = entry.data[CONF_SERIAL]
    if serial not in hass.data[DOMAIN]:
        _LOGGER.warning(f"Try not unload non-exist serial: {serial}")
        return True

    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        device = hass.data[DOMAIN][serial].get("devices")
        if device:
            device.cleanup()
            _LOGGER.info(f"Clean serial {serial}")
        else:
            _LOGGER.warning(f"Cannot find instance for serial: {serial}")

        hass.data[DOMAIN].pop(serial)
        if not hass.config_entries.async_entries(DOMAIN):
            hass.data.pop(DOMAIN)

    return unload_ok
