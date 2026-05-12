"""Base entity mixin for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from typing import Any

from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class BaseEntity(Entity):
    """Base mixin providing shared device_info for all Solar Manager entities.

    All Solar Manager entity classes (sensor, switch, number, button, light,
    select, time) share the same device_info structure. This mixin centralizes
    that logic and reads sw_version dynamically from the device instance.

    Subclasses MUST set these instance attributes before device_info is accessed:
        - self._device: The BaseDevice instance
        - self._model: The device model string
        - self._device_id: The device serial number / identifier
    """

    _device: Any
    _model: str
    _device_id: str

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": f"{self._model} {self._device_id}",
            "manufacturer": "@maybetaken",
            "model": self._model,
            "sw_version": self._device.sw_version,
        }
