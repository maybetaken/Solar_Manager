"""MakeSkyBlue device class for Solar Manager integration."""

from typing import Any

from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)
from homeassistant.core import HomeAssistant

from .base_device import BaseDevice


class MakeSkyBlueDevice(BaseDevice):
    """MakeSkyBlue device class for Solar Manager."""

    def __init__(self, hass: HomeAssistant, protocol_file: str) -> None:
        """Initialize the base device."""
        super().__init__(hass, protocol_file)
        self.parser = ModbusProtocolHelper(protocol_file)

    def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        device_info: dict[str, list[dict[str, Any]]] = {
            "sensor": [],
            "number": [],
            "select": [],
        }
        for register, details in self.protocol_data["registers"].items():
            name = details["name"]
            if details["access"] == "R":
                device_info["sensor"].append({"name": name, "register": register})
            elif details["access"] == "RW":
                if "range" in details:
                    device_info["number"].append({"name": name, "register": register})
                elif "enum" in details:
                    options = list(details["enum"].values())
                    device_info["select"].append(
                        {"name": name, "register": register, "options": options}
                    )
        return device_info
