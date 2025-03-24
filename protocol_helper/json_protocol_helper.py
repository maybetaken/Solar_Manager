"""Helper for handling JSON protocol files for Solar Manager."""

import json
import struct
from typing import Any, Dict
import crcmod.predefined
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class JsonProtocolHelper:
    """Class to handle JSON protocol files and Modbus communication."""

    def __init__(self, protocol_file: str) -> None:
        """Initialize the helper with the given protocol file."""
        self.protocol_file = protocol_file
        self.protocol_data = self._load_protocol()
        self.crc16 = crcmod.predefined.mkPredefinedCrcFun("modbus")

    def _load_protocol(self) -> Dict[str, Any]:
        """Load the protocol data from the JSON file."""
        with open(self.protocol_file, "r") as file:
            return json.load(file)

    def parse_data(self, data: bytes) -> Dict[str, Any]:
        """Parse the given data according to the protocol."""
        parsed_data = {}
        for register, details in self.protocol_data["registers"].items():
            start = int(register, 16) * 2
            length = 2 if details["type"] == "UINT16" else 4
            raw_value = data[start : start + length]
            value = struct.unpack(f">{details['type'][4:].lower()}", raw_value)[0]
            if details["scale"] != 1:
                value *= details["scale"]
            parsed_data[details["name"]] = value
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
        session = async_get_clientsession(hass)
        async with session.post(url, data=data) as response:
            response_data = await response.read()
            return response_data
