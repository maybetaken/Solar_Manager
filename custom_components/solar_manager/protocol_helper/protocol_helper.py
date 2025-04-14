"""Base class for handling protocol files for Solar Manager.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
import json
from typing import Any

import aiofiles
import crcmod.predefined

from homeassistant.core import HomeAssistant


class ProtocolHelper(ABC):
    """Base class to handle protocol files and Modbus communication."""

    def __init__(self, hass: HomeAssistant, protocol_file: str) -> None:
        """Initialize the helper with the given protocol file."""
        self._hass = hass
        self.protocol_file = protocol_file
        self.protocol_data: dict[str, Any] | None = None
        self.crc16 = crcmod.predefined.mkPredefinedCrcFun("modbus")
        self.callback = None
        self._update_callbacks: dict[str, Callable[[Any], None]] = {}

    async def load_protocol(self) -> dict[str, Any]:
        """Load the protocol data from the file asynchronously."""
        async with aiofiles.open(self.protocol_file) as file:
            data = await file.read()
            self.protocol_data = json.loads(data)
            return self.protocol_data

    def set_update_callback(
        self, register: str, callback: Callable[[Any], None]
    ) -> None:
        """Set callback for certain register to update value."""

        if register not in self._update_callbacks:
            self._update_callbacks[register] = callback

    @abstractmethod
    def register_callback(self, callback: callable) -> None:
        """Register a callback function to send data through mqtt."""

    @abstractmethod
    async def read_data(self, register_name: str) -> Any:
        """Read data from the device for a specific register."""

    @abstractmethod
    async def write_data(self, register_name: str, value: Any) -> None:
        """Write data to the device for a specific register."""

    @abstractmethod
    def pack_data(self, slave_id: int, address: int, value: int) -> bytes:
        """Pack data according to the protocol."""

    @abstractmethod
    async def send_data(self, hass: HomeAssistant, url: str, data: bytes) -> bytes:
        """Send data to the device and return the response."""
