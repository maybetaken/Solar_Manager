"""Base device class for Solar Manager integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from homeassistant.core import HomeAssistant


class BaseDevice(ABC):
    """Base device class for Solar Manager."""

    def __init__(self, hass: HomeAssistant, protocol_file: str) -> None:
        """Initialize the base device."""
        self.hass = hass
        self.protocol_file = protocol_file
        self.parser = None
        self.protocol_data = None

    async def load_protocol(self) -> None:
        """Load the protocol data asynchronously."""
        self.protocol_data = await self.parser.load_protocol()

    @abstractmethod
    def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
