"""Base device class for Solar Manager integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from homeassistant.core import HomeAssistant


class BaseDevice(ABC):
    """Base device class for Solar Manager."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the base device."""
        self.hass = hass
        self.protocol_file = protocol_file
        self.sn = sn
        self.model = model
        self.parser = None
        self.protocol_data = None

    async def load_protocol(self) -> None:
        """Load the protocol data asynchronously."""
        if self.parser is not None:
            self.protocol_data = await self.parser.load_protocol()

    @abstractmethod
    async def async_init(self) -> None:
        """Cleanup device."""

    @abstractmethod
    def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup device."""
