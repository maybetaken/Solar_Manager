"""The Solar Manager integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import _LOGGER, CONF_MODEL, CONF_SERIAL, DOMAIN
from .device_protocol.protocol_map import protocol_map
from .mqtt_manager import MQTTManager
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


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarManagerConfigEntry
) -> bool:
    """Set up Solar Manager from a config entry."""
    # Print the title and data
    print(f"Setting up entry with title: {entry.title}")
    print(f"Setting up entry with data: {entry.data}")

    hass.data.setdefault(DOMAIN, {})

    # Create API instance if not already created
    if "MQTT" not in hass.data[DOMAIN]:
        mqtt_manager = MQTTManager(hass, "192.168.31.71", 1883)
        hass.data[DOMAIN]["MQTT"] = mqtt_manager

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
    device = device_class(hass, protocol_file_path)
    solar_platforms = device.unpack_device_info()
    if serial not in hass.data[DOMAIN]:
        hass.data[DOMAIN][serial] = {}
    for platform, items in solar_platforms.items():
        for item in items:
            item_name = f"{model}_{serial}_{item['name']}"
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
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok and not hass.config_entries.async_entries(DOMAIN):
        hass.data.pop(DOMAIN)
    return unload_ok
