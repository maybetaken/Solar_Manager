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
from .ssdp import SSDPBroadcaster

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
type SolarManagerConfigEntry = ConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Solar Manager integration."""
    hass.data.setdefault(DOMAIN, {})
    # Initialize SSDP broadcaster for the entire integration
    if "broadcaster" not in hass.data[DOMAIN]:
        broadcaster = SSDPBroadcaster(hass, interval=5.0)
        hass.data[DOMAIN]["broadcaster"] = broadcaster
        await broadcaster.start()
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: SolarManagerConfigEntry
) -> bool:
    """Set up Solar Manager from a config entry."""

    _ = get_mqtt_manager(hass)
    hass.data.setdefault(DOMAIN, {})

    # Handle the protocol and device setup
    serial = entry.data[CONF_SERIAL]
    if serial not in hass.data[DOMAIN]:
        hass.data[DOMAIN][serial] = {"devices": []}

    for model_data in entry.data.get("models", []):
        model = model_data[CONF_MODEL]
        protocol = protocol_map.get(model)
        if protocol is None:
            _LOGGER.error("Protocol not found for model %s", model)
            continue

        device_class = device_class_map.get(model)
        if device_class is None:
            _LOGGER.error("Device class not found for model %s", model)
            continue

        protocol_file_path = (
            Path(__file__).parent / "device_protocol" / f"{protocol}.json"
        )
        device = device_class(hass, protocol_file_path, serial, model)

        await device.load_protocol()

        solar_platforms = await device.unpack_device_info()

        hass.data[DOMAIN][serial]["devices"].append(device)

        for platform, items in solar_platforms.items():
            for item in items:
                item["parser"] = device.parser
                item["model"] = model
                if platform not in hass.data[DOMAIN][serial]:
                    hass.data[DOMAIN][serial][platform] = []
                hass.data[DOMAIN][serial][platform].append(item)
            await hass.config_entries.async_forward_entry_setups(entry, [platform])

        await device.async_init()
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
        # Clean up devices
        devices = hass.data[DOMAIN][serial].get("devices", [])
        for device in devices:
            device.cleanup()
            _LOGGER.info("Cleaned up device for serial %s", serial)

        hass.data[DOMAIN].pop(serial)

        # Clean up broadcaster only if no config entries remain
        if not hass.config_entries.async_entries(DOMAIN):
            broadcaster = hass.data[DOMAIN].get("broadcaster")
            if broadcaster:
                await broadcaster.async_cleanup()
                _LOGGER.info("SSDP broadcaster cleaned up")
            hass.data.pop(DOMAIN)

    return unload_ok
