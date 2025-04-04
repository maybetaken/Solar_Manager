"""Helper for handling Modbus protocol files for Solar Manager."""

import struct
from typing import Any

from custom_components.solar_manager.const import _LOGGER
from homeassistant.core import HomeAssistant

from .protocol_helper import ProtocolHelper


class ModbusProtocolHelper(ProtocolHelper):
    """Class to handle Modbus protocol files and communication."""

    def __init__(self, protocol_file: str) -> None:
        """Initialize the helper with the given protocol file."""
        super().__init__(protocol_file)
        self._parsed_data: dict[str, Any] = {}

    async def read_data(self, register_name: str) -> Any:
        """Read data from the device for a specific register."""
        if self.protocol_data is None:
            self.protocol_data = await self.load_protocol()

        details = self.protocol_data["registers"].get(register_name)
        if not details:
            raise ValueError(f"Register {register_name} not found in protocol")

        if details["type"] == "UINT16":
            value = 1
        elif details["type"] == "UINT32":
            value = 56789
        else:
            value = 0

        if details["scale"] != 1:
            value *= details["scale"]

        return value

    async def write_data(self, register_name: str, value: Any) -> None:
        """Write data to the device for a specific register."""
        if self.protocol_data is None:
            self.protocol_data = await self.load_protocol()

        details = self.protocol_data["registers"].get(register_name)
        if not details:
            raise ValueError(f"Register {register_name} not found in protocol")
        _LOGGER.debug("register_name: %s, value: %s", register_name, value)

    def parse_data(self, data: bytes) -> None:
        """Parse the given data according to the protocol."""
        for register, details in self.protocol_data["registers"].items():
            start = int(register, 16) * 2
            length = 2 if details["type"] == "UINT16" else 4
            raw_value = data[start : start + length]
            value = struct.unpack(f">{details['type'][4:].lower()}", raw_value)[0]
            if details["scale"] != 1:
                value *= details["scale"]
            self._parsed_data[details["name"]] = value

    def pack_data(self, slave_id: int, address: int, value: int) -> bytes:
        """Pack data according to the protocol."""
        write_command = self.protocol_data["write_command"]
        packed_data = (
            struct.pack(">B", slave_id)
            + struct.pack(">B", write_command)
            + struct.pack(">H", address)
            + struct.pack(">H", value)
        )
        crc = self.crc16(packed_data)
        packed_data += struct.pack(">H", crc)
        return packed_data

    async def send_data(self, hass: HomeAssistant, url: str, data: bytes) -> bytes:
        """Send data to the device and return the response."""
        # This is a placeholder for actual Modbus communication
        return data
