"""Helper for handling Modbus protocol files for Solar Manager.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import struct
from typing import Any

from custom_components.solar_manager.const import _LOGGER

from homeassistant.core import HomeAssistant

from .protocol_helper import ProtocolHelper


class ModbusProtocolHelper(ProtocolHelper):
    """Class to handle Modbus protocol files and communication."""

    def __init__(self, hass: HomeAssistant, protocol_data: dict[str, Any]) -> None:
        """Initialize the ModbusProtocolHelper."""
        super().__init__(hass, protocol_data)

    async def read_data(self, register_name: str) -> Any:
        """Read data from the device for a specific register."""
        if self.protocol_data is None:
            self.protocol_data = await self.load_protocol()

        return None

    async def write_data(self, register_name: str, value: Any) -> None:
        """Write data to the device for a specific register."""
        if self.protocol_data is None:
            self.protocol_data = await self.load_protocol()

        details = self.protocol_data["registers"].get(register_name)
        if not details:
            raise ValueError(f"Register {register_name} not found in protocol")
        await self.callback(register_name, value)

    def parse_data(self, data: bytes, start_address: int = 0) -> dict[str, Any]:
        """Parse the given data starting from the specified address according to the protocol.

        Returns a dictionary with format {register_address: data}.
        """
        parsed_data = {}
        # Cache endianness and prefix
        endianness = self.protocol_data.get("endianness", "BE")
        endian_prefix = ">" if endianness == "BE" else "<"
        if endianness not in ("BE", "LE"):
            raise ValueError(f"Unsupported endianness: {endianness}")

        # Pre-compute register addresses and sort to process only relevant ones
        registers = [
            (register, details)
            for register, details in self.protocol_data["registers"].items()
            if int(register, 16) >= start_address
        ]
        registers.sort(key=lambda x: int(x[0], 16))

        for register, details in registers:
            reg_addr = int(register, 16)
            offset = reg_addr * 2 - start_address
            length = 2 if details["type"] == "UINT16" else 4
            if offset + length > len(data):
                break
            fmt = "H" if details["type"] == "UINT16" else "I"
            try:
                value = struct.unpack(
                    f"{endian_prefix}{fmt}", data[offset : offset + length]
                )[0]
                parsed_data[register] = value
            except struct.error as e:
                _LOGGER.error(
                    "Failed to parse register %s (%s): %s", register, details["name"], e
                )
                continue

        return parsed_data

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

    def register_callback(self, callback: callable) -> None:
        """Register a callback function to handle specific events."""
        self.callback = callback
