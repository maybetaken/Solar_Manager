"""Base device class for Solar Manager integration."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any
from homeassistant.core import HomeAssistant

from ..protocol_helper.modbus_protocol_helper import ProtocolHelper


class BaseDevice(ABC):
    """Base device class for Solar Manager."""

    def __init__(self, hass: HomeAssistant, protocol_file: str) -> None:
        """Initialize the base device."""
        self.hass = hass
        self.protocol_file = protocol_file
        self.protocol_data = self._load_protocol()
        self.parser = ProtocolHelper(protocol_file)

    def _load_protocol(self) -> dict[str, Any]:
        """Load the protocol data from the JSON file."""
        with open(self.protocol_file, "r") as file:
            return json.load(file)

    @abstractmethod
    def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        pass
