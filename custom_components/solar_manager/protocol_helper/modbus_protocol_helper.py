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
    "UINT8": ("B", 1),  # Unsigned 8-bit integer, 1 byte (New)
    "INT8": ("b", 1),  # Signed 8-bit integer, 1 byte (New)
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
                _LOGGER.error("Payload too short: %d bytes", len(data))
                return {}

            endianness = self.protocol_data.get("endianness", "BE")
            addressing_mode = self.protocol_data.get("addressing", "register")

            endian_prefix = ">" if endianness == "BE" else "<"

            slave_id, read_command, start_address, length = struct.unpack(
                f"{endian_prefix}BBHH", data[:6]
            )
            data_bytes = data[6:]
            read_command = read_command << 20

            parsed_data = {}

            if read_command in (1 << 20, 2 << 20):
                expected_bytes = (length + 7) // 8
                if len(data_bytes) < expected_bytes:
                    return {}
                for i in range(length):
                    reg_addr = read_command + start_address + i
                    reg_info = self.protocol_data["registers"].get(reg_addr)
                    if reg_info:
                        byte_idx = i // 8
                        bit_idx = i % 8
                        val = (data_bytes[byte_idx] >> bit_idx) & 0x01
                        parsed_data[reg_addr] = val

            else:
                total_bytes = len(data_bytes)
                byte_offset = 0

                while byte_offset < total_bytes:
                    if addressing_mode == "byte":
                        current_key = read_command + start_address + byte_offset
                    else:
                        current_key = read_command + start_address + (byte_offset // 2)

                    register_info = self.protocol_data["registers"].get(current_key)

                    if not register_info:
                        byte_offset += 1
                        continue

                    data_type = register_info.get("type")
                    if data_type not in TYPE_FORMATS:
                        byte_offset += 1
                        continue

                    if data_type == "STRING":
                        str_len = register_info.get("length", 0)
                        if byte_offset + str_len > total_bytes:
                            break

                        val_bytes = data_bytes[byte_offset : byte_offset + str_len]
                        val = (
                            val_bytes.decode("ascii", errors="replace")
                            .strip("\x00").strip("\x08")
                            .strip()
                        )
                        parsed_data[current_key] = val
                        byte_offset += str_len

                    else:
                        fmt, type_size = TYPE_FORMATS[data_type]

                        if byte_offset + type_size > total_bytes:
                            break

                        val = struct.unpack(
                            f"{endian_prefix}{fmt}",
                            data_bytes[byte_offset : byte_offset + type_size],
                        )[0]

                        parsed_data[current_key] = val

                        byte_offset += type_size

        except struct.error as e:
            _LOGGER.error("Failed to parse TLD payload: %s", e)
            return {}

        return parsed_data

    def pack_data(
        self, slave_id: int, address: int, value: Any, write_command: int = 6
    ) -> bytes:
        """Pack data for write commands."""
        address = address & 0xFFFF
        packed_data = b""

        if write_command == 6:
            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", int(value) & 0xFFFF)
            )
        elif write_command == 16:
            if not isinstance(value, (list, tuple)):
                return b""
            num_regs = len(value)
            data_bytes = b""
            for val in value:
                data_bytes += struct.pack(">H", int(val) & 0xFFFF)

            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", num_regs)
                + data_bytes
            )

        elif write_command == 5:
            coil_val = 0xFF00 if value else 0x0000
            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", coil_val)
            )

        return packed_data

    async def send_data(self, hass: HomeAssistant, url: str, data: bytes) -> bytes:
        return data

    def register_callback(self, callback: callable) -> None:
        self.callback = callback
