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
    "COIL": (None, None),  # Coil, handled as bits
    "DISCRETE_INPUT": (None, None),  # Discrete Input, handled as bits
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
        """Parse TLD format Modbus data: [slave_id:1][read_command:1][start_address:2][length:2][data].

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

            # Unpack slave_id, read_command, start_address, and length
            slave_id, read_command, start_address, length = struct.unpack(
                f"{endian_prefix}BBHH", data[:6]
            )
            data_bytes = data[6:]
            read_command = read_command << 20  # Retain original shift

            parsed_data = {}
            if read_command in (
                1 << 20,
                2 << 20,
            ):  # Handle COIL (0x01) or DISCRETE_INPUT (0x02)
                expected_bytes = (length + 7) // 8
                if len(data_bytes) < expected_bytes:
                    _LOGGER.error(
                        "Insufficient data for %s: need %d bytes, have %d",
                        "COIL" if read_command == (0x01 << 20) else "DISCRETE_INPUT",
                        expected_bytes,
                        len(data_bytes),
                    )
                    return {}

                for i in range(length):
                    register_address = read_command + start_address + i
                    register_info = self.protocol_data["registers"].get(
                        register_address
                    )
                    if not register_info or register_info.get("type") not in (
                        "COIL",
                        "DISCRETE_INPUT",
                    ):
                        continue

                    byte_index = i // 8
                    bit_index = i % 8
                    value = (data_bytes[byte_index] >> bit_index) & 0x01
                    parsed_data[register_address] = value
                    _LOGGER.debug(
                        "Parsed register 0x%08X: type=%s, value=%s",
                        register_address,
                        register_info.get("type"),
                        value,
                    )
            else:  # Handle registers (0x03, 0x04, etc.)
                byte_offset = 0
                i = 0
                while i < length:
                    register_address = read_command + start_address + i
                    register_info = self.protocol_data["registers"].get(
                        register_address
                    )

                    if not register_info:
                        byte_offset += 2
                        i += 1
                        continue

                    data_type = register_info.get("type")
                    if data_type not in TYPE_FORMATS:
                        _LOGGER.error(
                            "Unsupported data type %s for register 0x%08X",
                            data_type,
                            register_address,
                        )
                        byte_offset += 2
                        i += 1
                        continue

                    if data_type == "STRING":
                        str_length = register_info.get("length")
                        if not isinstance(str_length, int) or str_length <= 0:
                            _LOGGER.error(
                                "Invalid or missing length for STRING register 0x%08X",
                                register_address,
                            )
                            byte_offset += 2
                            i += 1
                            continue

                        if byte_offset + str_length > len(data_bytes):
                            _LOGGER.error(
                                "Insufficient data for STRING register 0x%08X: need %d bytes, have %d",
                                register_address,
                                str_length,
                                len(data_bytes) - byte_offset,
                            )
                            break

                        str_bytes = data_bytes[byte_offset : byte_offset + str_length]
                        value = (
                            str_bytes.decode("ascii", errors="replace")
                            .rstrip("\x00")
                            .rstrip()
                        )
                        parsed_data[register_address] = value
                        byte_offset += str_length
                        i += (str_length + 1) // 2
                        _LOGGER.debug(
                            "Parsed register 0x%08X: type=STRING, value=%s",
                            register_address,
                            value,
                        )
                    else:
                        fmt, byte_size = TYPE_FORMATS[data_type]
                        if byte_offset + byte_size > len(data_bytes):
                            _LOGGER.error(
                                "Insufficient data for register 0x%08X: need %d bytes, have %d",
                                register_address,
                                byte_size,
                                len(data_bytes) - byte_offset,
                            )
                            break

                        value = struct.unpack(
                            f"{endian_prefix}{fmt}",
                            data_bytes[byte_offset : byte_offset + byte_size],
                        )[0]
                        parsed_data[register_address] = value
                        byte_offset += byte_size
                        i += byte_size // 2
                        _LOGGER.debug(
                            "Parsed register 0x%08X: type=%s, value=%s",
                            register_address,
                            data_type,
                            value,
                        )

        except struct.error as e:
            _LOGGER.error("Failed to parse TLD payload: %s", e)
            return {}

        return parsed_data

    def pack_data(
        self, slave_id: int, address: int, value: Any, write_command: int = 6
    ) -> bytes:
        """Pack data according to the protocol for Modbus commands.

        Args:
            slave_id: Modbus slave ID (1-247).
            address: Register or coil address (0-65535).
            value: Value(s) to write (bool/int for 0x05, int/float for 0x06, list for 0x10).
            write_command: Modbus function code (5, 6, or 16).

        Returns:
            Packed bytes in TLD format: [slave_id:1][write_command:1][address:2][value(s) or num_regs:2][data][crc:2].
        """
        address = address & 0xFFFF
        packed_data = b""

        if write_command == 5:  # Write Single Coil
            if isinstance(value, bool):
                coil_value = 0xFF00 if value else 0x0000
            elif isinstance(value, int) and value in (0, 1):
                coil_value = 0xFF00 if value == 1 else 0x0000
            else:
                _LOGGER.error(
                    "Value for coil must be bool or int (0/1), got %s", type(value)
                )
                return b""
            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", coil_value)
            )
        elif write_command == 6:  # Write Single Register
            if not isinstance(value, (int, float)):
                _LOGGER.error(
                    "Value for single register must be int or float, got %s",
                    type(value),
                )
                return b""
            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", int(value) & 0xFFFF)
            )
        elif write_command == 16:  # Write Multiple Registers
            if not isinstance(value, (list, tuple)):
                _LOGGER.error(
                    "Value for multiple registers must be a list or tuple, got %s",
                    type(value),
                )
                return b""
            num_regs = len(value)
            if num_regs == 0 or num_regs > 123:
                _LOGGER.error(
                    "Invalid number of registers: %d (must be 1-123)", num_regs
                )
                return b""
            byte_count = num_regs * 2
            data_bytes = b""
            for val in value:
                if not isinstance(val, (int, float)):
                    _LOGGER.error(
                        "Each value for multiple registers must be int or float, got %s",
                        type(val),
                    )
                    return b""
                data_bytes += struct.pack(">H", int(val) & 0xFFFF)
            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", num_regs)
                + struct.pack(">B", byte_count)
                + data_bytes
            )
        else:
            _LOGGER.error("Unsupported write command: %d", write_command)
            return b""

        # crc = self.crc16(packed_data)
        # packed_data += struct.pack(">H", crc)
        return packed_data

    async def send_data(self, hass: HomeAssistant, url: str, data: bytes) -> bytes:
        """Send data to the device and return the response."""
        # Placeholder for actual Modbus communication
        return data

    def register_callback(self, callback: callable) -> None:
        """Register a callback function to handle specific events."""
        self.callback = callback
