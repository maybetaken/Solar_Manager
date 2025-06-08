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

TYPE_FORMATS = {
    "UINT16": ("H", 2),  # Unsigned 16-bit integer, 2 bytes
    "INT16": ("h", 2),  # Signed 16-bit integer, 2 bytes
    "UINT32": ("I", 4),  # Unsigned 32-bit integer, 4 bytes
    "INT32": ("i", 4),  # Signed 32-bit integer, 4 bytes
    "FLOAT": ("f", 4),  # 32-bit float, 4 bytes
    "STRING": (None, None),  # String, handled separately
}


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

        await self.callback(register_name, value)

    def parse_data(self, data: bytes) -> dict[int, Any]:
        """Parse TLD format Modbus data: [start_address:2][length:2][data:L*2].

        Returns a dictionary with format {register_address: value}.
        """
        try:
            if len(data) < 6:
                _LOGGER.error("Payload too short for TLD format: %d bytes", len(data))
                return {}

            # Determine endianness
            endianness = self.protocol_data.get("endianness", "BE")
            endian_prefix = ">" if endianness == "BE" else "<"
            if endianness not in ("BE", "LE"):
                _LOGGER.warning(
                    "Unsupported endianness: %s, defaulting to BE", endianness
                )
                endian_prefix = ">"

            # Unpack start address and length
            _, read_command, start_address, length = struct.unpack(
                f"{endian_prefix}BBHH", data[:6]
            )
            data_bytes = data[6:]
            read_command = read_command << 20

            parsed_data = {}
            byte_offset = 0
            i = 0
            while i < length:
                register_address = read_command + start_address + i
                # Use integer register_address directly for lookup
                register_info = self.protocol_data["registers"].get(register_address)

                if not register_info:
                    # Skip 2 bytes (assume UINT16 size for unknown registers)
                    byte_offset += 2
                    i += 1
                    continue

                data_type = register_info.get("type")
                if data_type not in TYPE_FORMATS:
                    _LOGGER.error(
                        "Unsupported data type %s for register 0x%04X",
                        data_type,
                        register_address,
                    )
                    byte_offset += 2
                    i += 1
                    continue

                if data_type == "STRING":
                    # Handle STRING type
                    str_length = register_info.get("length")
                    if not isinstance(str_length, int) or str_length <= 0:
                        _LOGGER.error(
                            "Invalid or missing length for STRING register 0x%04X",
                            register_address,
                        )
                        byte_offset += 2
                        i += 1
                        continue

                    # Ensure enough data remains
                    if byte_offset + str_length > len(data_bytes):
                        _LOGGER.error(
                            "Insufficient data for STRING register 0x%04X: need %d bytes, have %d",
                            register_address,
                            str_length,
                            len(data_bytes) - byte_offset,
                        )
                        break

                    # Read and decode string
                    str_bytes = data_bytes[byte_offset : byte_offset + str_length]
                    # Decode as ASCII, replace invalid chars, strip nulls and padding
                    value = (
                        str_bytes.decode("ascii", errors="replace")
                        .rstrip("\x00")
                        .rstrip()
                    )
                    parsed_data[register_address] = value
                    byte_offset += str_length
                    # Increment i by number of registers (each register = 2 bytes)
                    i += (str_length + 1) // 2  # Ceiling division

                    _LOGGER.debug(
                        "Parsed register 0x%04X: type=STRING, value=%s",
                        register_address,
                        value,
                    )
                else:
                    # Handle numeric types (UINT16, UINT32, FLOAT)
                    fmt, byte_size = TYPE_FORMATS[data_type]

                    # Check if enough data remains
                    if byte_offset + byte_size > len(data_bytes):
                        _LOGGER.error(
                            "Insufficient data for register 0x%04X: need %d bytes, have %d",
                            register_address,
                            byte_size,
                            len(data_bytes) - byte_offset,
                        )
                        break

                    # Unpack the value
                    value = struct.unpack(
                        f"{endian_prefix}{fmt}",
                        data_bytes[byte_offset : byte_offset + byte_size],
                    )[0]

                    parsed_data[register_address] = value
                    byte_offset += byte_size
                    i += byte_size // 2  # Each register is 2 bytes

                    _LOGGER.debug(
                        "Parsed register 0x%04X: type=%s, value=%s",
                        register_address,
                        data_type,
                        value,
                    )

        except struct.error as e:
            _LOGGER.error("Failed to parse TLD payload: %s", e)
            return {}

        return parsed_data

    def pack_data(
        self, slave_id: int, address: int, value: int, write_command: int = 6
    ) -> bytes:
        """Pack data according to the protocol."""
        address = address & 0xFFFF
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
        # Placeholder for actual Modbus communication
        return data

    def register_callback(self, callback: callable) -> None:
        """Register a callback function to handle specific events."""
        self.callback = callback
