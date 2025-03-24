"""Parser for different device protocols for Solar Manager."""

import json
from typing import Any
import struct
import crcmod.predefined
import aiofiles


class ProtocolHelper:
    """Class to parse and pack device protocols."""

    def __init__(self, protocol_file: str) -> None:
        """Initialize the parser with the given protocol file."""
        self.protocol_file = protocol_file
        self.protocol_data = None
        self.crc16 = crcmod.predefined.mkPredefinedCrcFun("modbus")

    async def load_protocol(self) -> dict[str, Any]:
        """Load the protocol data from the JSON file asynchronously."""
        async with aiofiles.open(self.protocol_file, "r") as file:
            data = await file.read()
            self.protocol_data = json.loads(data)
            return self.protocol_data

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
        print(f"register_name: {register_name}, value: {value}")

    def parse_data(self, data: bytes) -> dict[str, Any]:
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
