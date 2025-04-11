"""Helper for handling Modbus protocol files for Solar Manager."""

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
        self._parsed_data: dict[str, Any] = {}

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

    def parse_data(self, data: bytes, start_address: int = 0) -> None:
        """Parse the given data starting from the specified address according to the protocol."""
        offset = 0
        for register, details in self.protocol_data["registers"].items():
            reg_addr = int(register, 16)
            if reg_addr < start_address:
                continue

            length = 2 if details["type"] == "UINT16" else 4
            fmt = "H" if details["type"] == "UINT16" else "I"

            if offset + length > len(data):
                break

            endianness = self.protocol_data.get("endianness", "BE")
            if endianness == "BE":
                endian_prefix = ">"
            elif endianness == "LE":
                endian_prefix = "<"
            else:
                raise ValueError(f"Unsupported endianness: {endianness}")

            raw_value = data[offset : offset + length]
            try:
                value = struct.unpack(f"{endian_prefix}{fmt}", raw_value)[0]

            except struct.error as e:
                _LOGGER.error("Failed to parse register %s: %s", register, e)
                continue

            # Apply scaling if necessary
            if details.get("scale", 1) != 1:
                value *= details["scale"]

            previous_value = self._parsed_data.get(register)

            if previous_value != value:
                self._parsed_data[register] = value
                if register in self._update_callbacks:
                    try:
                        self._hass.loop.call_soon_threadsafe(
                            lambda reg=register, val=value: self._hass.loop.create_task(
                                self._update_callbacks[reg](val)
                            )
                        )
                    except RuntimeError as e:
                        _LOGGER.error(
                            f"Failed to schedule callback for {register} due to event loop issue: {e}"
                        )
                    except AttributeError as e:
                        _LOGGER.error(f"Invalid hass.loop for {register}: {e}")

            offset += length

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
