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

    def parse_data(self, data: bytes) -> dict[str, Any]:
        """Parse TLD format Modbus data: [start_address:2][length:2][data:L*2].

        Returns a dictionary with format {register_address: data}.
        """
        try:
            if len(data) < 4:
                _LOGGER.error("Payload too short for TLD format: %d bytes", len(data))
                return {}

            endianness = self.protocol_data.get("endianness", "BE")
            endian_prefix = ">" if endianness == "BE" else "<"
            if endianness not in ("BE", "LE"):
                _LOGGER.warning(
                    "Unsupported endianness: %s, defaulting to BE", endianness
                )
                endian_prefix = ">"

            start_address, length = struct.unpack(f"{endian_prefix}HH", data[:4])
            data_bytes = data[4:]

            expected_bytes = length * 2
            if len(data_bytes) != expected_bytes:
                _LOGGER.error(
                    "Invalid data length: expected %d bytes, got %d",
                    expected_bytes,
                    len(data_bytes),
                )
                return {}

            parsed_data = {}
            for i in range(length):
                register = f"0x{(start_address + i):02X}"
                value = struct.unpack(
                    f"{endian_prefix}H", data_bytes[i * 2 : (i + 1) * 2]
                )[0]
                parsed_data[register] = value

            _LOGGER.debug(
                "Parsed TLD: start_address=0x%04X, length=%d, registers=%s",
                start_address,
                length,
                list(parsed_data.keys()),
            )
        except struct.error as e:
            _LOGGER.error("Failed to parse TLD payload: %s", e)
            return {}

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
