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
            # 新增: 寻址模式 'register' (默认, 兼容旧设备) 或 'byte' (极空BMS)
            addressing_mode = self.protocol_data.get("addressing", "register")

            endian_prefix = ">" if endianness == "BE" else "<"

            slave_id, read_command, start_address, length = struct.unpack(
                f"{endian_prefix}BBHH", data[:6]
            )
            data_bytes = data[6:]
            read_command = read_command << 20

            parsed_data = {}

            # 处理位操作 (Coil/Discrete)
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

            # 处理寄存器数据
            else:
                total_bytes = len(data_bytes)
                byte_offset = 0

                # 使用字节偏移量循环，而不是寄存器索引
                while byte_offset < total_bytes:
                    # 计算当前的 Key
                    if addressing_mode == "byte":
                        # 字节寻址模式：Key = 起始地址 + 当前字节偏移量
                        # 适合 JK-BMS 这种把地址当偏移量用的协议
                        current_key = read_command + start_address + byte_offset
                    else:
                        # 寄存器寻址模式 (标准 Modbus)：Key = 起始地址 + (偏移量 / 2)
                        # 适合 MakeSkyBlue 等标准设备
                        current_key = read_command + start_address + (byte_offset // 2)

                    register_info = self.protocol_data["registers"].get(current_key)

                    # 如果当前地址没有定义，跳过 1 个字节继续尝试
                    # (标准模式下通常跳过2字节，但为了鲁棒性，逐字节扫描也无妨，只要Key对不上)
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
                            .strip("\x00")
                            .strip()
                        )
                        parsed_data[current_key] = val
                        byte_offset += str_len

                    else:
                        fmt, type_size = TYPE_FORMATS[data_type]

                        # 检查剩余长度是否足够
                        if byte_offset + type_size > total_bytes:
                            break

                        val = struct.unpack(
                            f"{endian_prefix}{fmt}",
                            data_bytes[byte_offset : byte_offset + type_size],
                        )[0]

                        parsed_data[current_key] = val

                        # ★ 核心逻辑：根据数据类型实际大小前进
                        # UINT8 跳 1 字节, UINT16 跳 2 字节, UINT32 跳 4 字节
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

        # 写入单个寄存器 (Modbus 协议底层写入最小单位通常是 2字节)
        # 即使是 UINT8，通常也是写入一个寄存器，设备取低位
        if write_command == 6:
            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", int(value) & 0xFFFF)
            )
        # 写入多个寄存器 (功能码 16)
        elif write_command == 16:
            if not isinstance(value, (list, tuple)):
                return b""
            num_regs = len(value)
            byte_count = num_regs * 2
            data_bytes = b""
            for val in value:
                data_bytes += struct.pack(">H", int(val) & 0xFFFF)

            packed_data = (
                struct.pack(">B", slave_id)
                + struct.pack(">B", write_command)
                + struct.pack(">H", address)
                + struct.pack(">H", num_regs)
                + struct.pack(">B", byte_count)
                + data_bytes
            )

        # 保持对 Coil (5) 的支持...
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
