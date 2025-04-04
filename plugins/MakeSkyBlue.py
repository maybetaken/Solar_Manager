"""MakeSkyBlue device class for Solar Manager integration."""

import logging
from typing import Any

from custom_components.solar_manager.mqtt_helper import mqtt_global
from custom_components.solar_manager.protocol_helper.modbus_protocol_helper import (
    ModbusProtocolHelper,
)
from homeassistant.core import HomeAssistant

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)


class MakeSkyBlueDevice(BaseDevice):
    """MakeSkyBlue device class for Solar Manager."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the base device."""
        super().__init__(hass, protocol_file, sn, model)
        self.parser = ModbusProtocolHelper(protocol_file)
        mqtt_manager = mqtt_global.get_mqtt_manager()
        mqtt_manager.register_callback(
            sn,
            self.handle_notify,
        )

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

    async def handle_notify(self, topic, payload):
        """Handle MQTT notifications.

        Args:
            topic (str): The MQTT topic of the notification.
            payload (Any): The payload of the notification.

        """
        _LOGGER.info("[callback ] %s: %s", topic, payload)
