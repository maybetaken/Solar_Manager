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
        self.parser = ModbusProtocolHelper(hass, protocol_file)
        self.slave_id = 1
        self.read_command = 3
        self.write_command = 6
        self.total_length = 217
        self.start_address = 0
        self.mqtt_manager = mqtt_global.get_mqtt_manager(hass)
        self.parser.register_callback(self.handle_cmd)

    async def async_init(self):
        """Async part of initialization."""
        await self.mqtt_manager.register_callback(
            self.sn,
            self.handle_notify,
        )

    def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into different groups."""
        self.slave_id = int(self.parser.protocol_data["slave_id"])
        self.read_command = int(self.parser.protocol_data["read_command"])
        self.write_command = int(self.parser.protocol_data["write_command"])
        self.total_length = int(self.parser.protocol_data["register_total_length"])
        self.start_address = int(self.parser.protocol_data["register_start_address"])

        device_info: dict[str, list[dict[str, Any]]] = {
            "sensor": [],
            "number": [],
            "select": [],
            "switch": [],
        }

        for register, details in self.protocol_data["registers"].items():
            name = details["name"]

            if details["access"] == "R":
                # Check if the register has an enum mapping
                if "enum" in details:
                    # Convert enum keys from string to int
                    enum_mapping = {
                        int(key, 16): value for key, value in details["enum"].items()
                    }
                    device_info["sensor"].append(
                        {
                            "name": name,
                            "register": register,
                            "enum_mapping": enum_mapping,
                        }
                    )
                else:
                    device_info["sensor"].append({"name": name, "register": register})

            elif details["access"] == "RW":
                if "range" in details:
                    device_info["number"].append({"name": name, "register": register})
                elif "enum" in details:
                    options = list(details["enum"].values())
                    device_info["select"].append(
                        {"name": name, "register": register, "options": options}
                    )

            elif details["access"] == "SW":
                device_info["switch"].append({"name": name, "register": register})

        return device_info

    async def handle_notify(self, topic, payload):
        """Handle MQTT notifications.

        Args:
            topic (str): The MQTT topic of the notification.
            payload (Any): The payload of the notification.

        """
        self.parser.parse_data(payload, self.start_address)

    def handle_cmd(self, cmd: str, value: Any) -> None:
        """Handle commands from the user.

        Args:
            cmd (str): The command to handle.
            value (Any): The value associated with the command.

        """
        topic = self.sn
        data: any = None
        if isinstance(value, str):
            topic += "/" + cmd
            data = value
        elif isinstance(value, int):
            topic += "/" + self.model + "/" + str(self.slave_id)
            data = self.parser.pack_data(self.slave_id, int(cmd, 16), value)
        elif isinstance(value, float):
            topic += "/" + self.model + "/" + str(self.slave_id)
            # TO-DO correct me
            data = self.parser.pack_data(
                self.slave_id,
                int(cmd, 16),
                int(value / self.protocol_data["registers"][cmd].get("scale", 1)),
            )
        else:
            _LOGGER.error("Unsupported value type: %s", type(value))
            return

        self.mqtt_manager.publish(topic, data)

    def cleanup(self) -> None:
        """Cleanup device."""
        self.mqtt_manager.unregister_callback(self.sn)
        self.parser = None
        self.mqtt_manager = None
        self.protocol_data = None
        self.hass = None
