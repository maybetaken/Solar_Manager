"""The Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import _LOGGER, CONF_MODEL, CONF_SERIAL, DOMAIN
from .device_protocol.device_config import DEVICE_CLASS_MAP, PROTOCOL_MAP
from .mqtt_helper.mqtt_global import get_mqtt_manager
from .ssdp import SSDPBroadcaster

# List the platforms that you want to support.
_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]

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
    model = entry.data[CONF_MODEL]

    if serial not in hass.data[DOMAIN]:
        hass.data[DOMAIN][serial] = {"devices": []}

    protocol = PROTOCOL_MAP.get(model)
    if protocol is None:
        _LOGGER.error("Protocol not found for model %s", model)
        return False

    device_class = DEVICE_CLASS_MAP.get(model)
    if device_class is None:
        _LOGGER.error("Device class not found for model %s", model)
        return False

    protocol_file_path = Path(__file__).parent / "device_protocol" / f"{protocol}.json"
    device = device_class(hass, protocol_file_path, serial, model)

    await device.load_protocol()

    solar_platforms = await device.unpack_device_info()

    hass.data[DOMAIN][serial]["devices"].append(device)

    for platform, items in solar_platforms.items():
        for item in items:
            item["parser"] = device.parser
            item["device"] = device
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
        _LOGGER.warning(f"Try to unload non-existent serial: {serial}")
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
