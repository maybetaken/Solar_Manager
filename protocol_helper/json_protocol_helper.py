"""Helper for handling JSON protocol files for Solar Manager."""

import struct
from typing import Any

from custom_components.solar_manager.const import _LOGGER
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .protocol_helper import ProtocolHelper


class JsonProtocolHelper(ProtocolHelper):
    """Class to handle JSON protocol files and Modbus communication."""

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
        session = async_get_clientsession(hass)
        async with session.post(url, data=data) as response:
            return await response.read()
