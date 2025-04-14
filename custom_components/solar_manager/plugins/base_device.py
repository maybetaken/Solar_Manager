"""Base device class for Solar Manager integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
import json
import logging

from custom_components.solar_manager.mqtt_helper import mqtt_global

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

# Clear diagnostics after 30 seconds of no updates
DIAGNOSTICS_CLEAR_INTERVAL = timedelta(seconds=30)


class BaseDevice(ABC):
    """Base device class for Solar Manager."""

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the base device."""
        self.hass = hass
        self.protocol_file = protocol_file
        self.sn = sn
        self.model = model
        self.parser = None
        self.protocol_data = None
        self.mqtt_manager = mqtt_global.get_mqtt_manager(hass)
        self._diagnostics = {
            "ssid": None,
            "rssi": None,
            "led": None,
        }
        self._diagnostic_entities = {}  # Store diagnostic entities
        self._clear_diagnostics_task = None

    def register_diagnostic_entity(self, sensor_name: str, entity: any) -> None:
        """Register a diagnostic entity."""
        self._diagnostic_entities[sensor_name] = entity
        _LOGGER.debug("Registered diagnostic entity %s for %s", sensor_name, self.sn)

    def unregister_diagnostic_entity(self, sensor_name: str) -> None:
        """Unregister a diagnostic entity."""
        if sensor_name in self._diagnostic_entities:
            self._diagnostic_entities[sensor_name] = None
            _LOGGER.debug(
                "Unregistered diagnostic entity %s for %s", sensor_name, self.sn
            )

    async def load_protocol(self) -> None:
        """Load the protocol data asynchronously."""
        if self.parser is not None:
            self.protocol_data = await self.parser.load_protocol()

    async def async_init(self) -> None:
        """Initialize the device."""
        await self.mqtt_manager.register_callback(
            f"{self.sn}/diagnostics",
            self.handle_diagnostics,
        )
        await self.mqtt_manager.register_callback(
            f"{self.sn}/notify",
            self.handle_notify,
        )
        # Start diagnostics clear timer
        self._reset_clear_diagnostics_timer()

    def _reset_clear_diagnostics_timer(self) -> None:
        """Reset the diagnostics clear timer."""
        if self._clear_diagnostics_task:
            self._clear_diagnostics_task()
        self._clear_diagnostics_task = async_track_time_interval(
            self.hass, self._clear_diagnostics, DIAGNOSTICS_CLEAR_INTERVAL
        )

    async def _clear_diagnostics(self, now=None) -> None:
        """Clear diagnostics data after timeout."""
        self._diagnostics["ssid"] = None
        self._diagnostics["rssi"] = None
        self._diagnostics["led"] = None
        _LOGGER.debug("Cleared diagnostics data for %s", self.sn)
        # Update entities
        for sensor_name, entity in self._diagnostic_entities.items():
            if entity is not None:
                entity.schedule_update_ha_state()
                _LOGGER.debug(
                    "Directly updated entity %s for %s due to diagnostics clear",
                    sensor_name,
                    self.sn,
                )

    async def handle_diagnostics(self, topic: str, payload: str) -> None:
        """Handle diagnostics JSON data from MQTT."""
        try:
            data = json.loads(payload)
            await self.update_diagnostics(data)
        except json.JSONDecodeError as e:
            _LOGGER.error("Invalid JSON payload for diagnostics %s: %s", self.sn, e)
        except (KeyError, TypeError, ValueError) as e:
            _LOGGER.error("Error handling diagnostics for %s: %s", self.sn, e)

    async def update_diagnostics(self, data: dict[str, any]) -> None:
        """Update diagnostics information from JSON data."""
        try:
            self._diagnostics["ssid"] = data.get("ssid")
            self._diagnostics["rssi"] = data.get("rssi")
            self._diagnostics["led"] = data.get("led")
            _LOGGER.debug("Diagnostics updated for %s: %s", self.sn, self._diagnostics)
            # Reset clear timer
            self._reset_clear_diagnostics_timer()
            # Directly update registered diagnostic entities
            for sensor_name, entity in self._diagnostic_entities.items():
                if entity is not None:
                    entity.schedule_update_ha_state()
                    _LOGGER.debug(
                        "Directly updated entity %s for %s", sensor_name, self.sn
                    )
        except KeyError as e:
            _LOGGER.error(
                "Missing key in diagnostics data for device %s: %s", self.sn, e
            )
        except TypeError as e:
            _LOGGER.error(
                "Invalid type in diagnostics data for device %s: %s", self.sn, e
            )

    def get_diagnostics(self) -> dict[str, any]:
        """Return diagnostics information."""
        return self._diagnostics.copy()

    async def set_led(self, state: bool) -> None:
        """Set LED state via MQTT."""
        self._diagnostics["led"] = state
        try:
            topic = f"{self.sn}/control/led"
            payload = json.dumps({"led": state})
            await self.mqtt_manager.publish(topic, payload)
            _LOGGER.debug("Published LED state %s to %s", state, topic)
            # Reset clear timer
            self._reset_clear_diagnostics_timer()
            # Update entities
            for sensor_name, entity in self._diagnostic_entities.items():
                if entity is not None:
                    entity.schedule_update_ha_state()
                    _LOGGER.debug(
                        "Directly updated entity %s for %s", sensor_name, self.sn
                    )
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            _LOGGER.error("Error setting LED for %s: %s", self.sn, e)

    def unpack_device_info(self) -> dict[str, list[dict[str, any]]]:
        """Unpack device information into different groups."""
        device_info: dict[str, list[dict[str, any]]] = {
            "sensor": [],
            "number": [],
            "select": [],
            "switch": [],
        }

        device_info["sensor"].extend(
            [
                {
                    "name": "SSID",
                    "diagnostic": True,
                    "icon": "mdi:wifi",
                },
                {
                    "name": "RSSI",
                    "diagnostic": True,
                    "unit": "dBm",
                    "icon": "mdi:wifi-strength-2",
                },
            ]
        )
        device_info["switch"].append(
            {
                "name": "LED",
                "diagnostic": True,
                "icon": "mdi:led-on",
            }
        )

        return device_info

    @abstractmethod
    async def handle_notify(self, topic: str, payload: str) -> None:
        """Handle device-specific MQTT notifications (to be overridden by subclasses)."""

    @abstractmethod
    async def handle_cmd(self, cmd: str, value: any) -> None:
        """Handle commands from the user (to be overridden by subclasses)."""

    def cleanup(self) -> None:
        """Cleanup device."""
        self.mqtt_manager.unregister_callback(f"{self.sn}/diagnostics")
        self.mqtt_manager.unregister_callback(f"{self.sn}/notify")

        self._diagnostic_entities.clear()
        if self._clear_diagnostics_task:
            self._clear_diagnostics_task()
            self._clear_diagnostics_task = None
        self.parser = None
        self.mqtt_manager = None
        self.protocol_data = None
        self.hass = None

    @abstractmethod
    def setup_protocol(self) -> None:
        """Set up device-specific protocol parameters."""
