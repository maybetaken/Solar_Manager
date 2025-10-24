"""
Base device class for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
import json
import logging
from typing import Optional

from custom_components.solar_manager.mqtt_helper import mqtt_global
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

# Clear diagnostics and data after 120 seconds of no updates
CLEAR_INTERVAL = timedelta(seconds=120)


class BaseDevice(ABC):
    """Base device class for Solar Manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        protocol_file: str,
        sn: str,
        model: str,
        topic_segment: Optional[str] = None,
        enable_diagnostics: bool = True,
    ) -> None:
        """Initialize the base device.

        Args:
            hass: HomeAssistant instance.
            protocol_file: Path to the protocol file.
            sn: Serial number of the device.
            model: Device model.
            topic_segment: Device-specific topic segment (e.g., 'device').
            enable_diagnostics: Enable diagnostics functionality.
        """
        self.hass = hass
        self.protocol_file = protocol_file
        self.sn = sn
        self.model = model
        self.parser = None
        self.protocol_data = None
        self.mqtt_manager = mqtt_global.get_mqtt_manager(hass)
        self._topic_segment = topic_segment or ""
        self._enable_diagnostics = enable_diagnostics
        self.cmd_topic = self._build_topic("control", "cmd")

        self._diagnostics = (
            {"ssid": None, "rssi": None, "led": None} if enable_diagnostics else {}
        )
        self._data_dict = {}  # Store parsed data as {name: data}
        self._diagnostic_entities = (
            {} if enable_diagnostics else {}
        )  # Store diagnostic entities
        self._entities = {}  # Store regular entities
        self._diagnostics_clear_task = None
        self._notify_clear_task = None

    def _build_topic(self, *parts: str) -> str:
        """Build an MQTT topic with sn and optional device-specific segment."""
        base = (
            f"{self.sn}/{self._topic_segment}" if self._topic_segment else f"{self.sn}"
        )
        return f"{base}/{'/'.join(parts)}"

    async def async_init(self) -> None:
        """Set up the device asynchronously."""
        await self.load_protocol()
        if self._enable_diagnostics:
            await self.mqtt_manager.register_callback(
                self._build_topic("diagnostics"),
                self.handle_diagnostics,
            )
        await self.mqtt_manager.register_callback(
            self._build_topic("notify"),
            self.handle_notify,
        )
        await self.mqtt_manager.register_callback(
            self._build_topic("online"),
            self.handle_online,
        )
        await self.send_config()

        if self._enable_diagnostics:
            self._reset_diagnostics_clear_timer()
        self._reset_notify_clear_timer()

    async def handle_online(self, topic: str, payload: bytes) -> None:
        """Handle device online message."""
        _LOGGER.info("Device %s is online, sending configuration", self.sn)
        await self.send_config()

    @abstractmethod
    async def send_config(self) -> None:
        """Send device-specific configuration to the device."""

    def register_entity(self, name: str, entity: any) -> None:
        """Register a regular entity."""
        self._entities[name] = entity
        _LOGGER.debug("Registered entity %s for %s", name, self.sn)

    def unregister_entity(self, name: str) -> None:
        """Unregister a regular entity."""
        if name in self._entities:
            self._entities[name] = None
            _LOGGER.debug("Unregistered entity %s for %s", name, self.sn)

    def register_diagnostic_entity(self, sensor_name: str, entity: any) -> None:
        """Register a diagnostic entity if enabled."""
        if not self._enable_diagnostics:
            _LOGGER.debug("Diagnostic entity registration disabled for %s", self.sn)
            return
        self._diagnostic_entities[sensor_name] = entity
        _LOGGER.debug("Registered diagnostic entity %s for %s", sensor_name, self.sn)

    def unregister_diagnostic_entity(self, sensor_name: str) -> None:
        """Unregister a diagnostic entity if enabled."""
        if not self._enable_diagnostics:
            return
        if sensor_name in self._diagnostic_entities:
            self._diagnostic_entities[sensor_name] = None
            _LOGGER.debug(
                "Unregistered diagnostic entity %s for %s", sensor_name, self.sn
            )

    async def load_protocol(self) -> None:
        """Load the protocol data asynchronously."""
        if self.parser is not None:
            self.protocol_data = await self.parser.load_protocol()

    def _reset_diagnostics_clear_timer(self) -> None:
        """Reset the diagnostics clear timer if enabled."""
        if not self._enable_diagnostics:
            return
        if self._diagnostics_clear_task:
            self._diagnostics_clear_task()
        self._diagnostics_clear_task = async_track_time_interval(
            self.hass, self._clear_diagnostics, CLEAR_INTERVAL
        )

    def _reset_notify_clear_timer(self) -> None:
        """Reset the notify clear timer."""
        if self._notify_clear_task:
            self._notify_clear_task()
        self._notify_clear_task = async_track_time_interval(
            self.hass, self._clear_notify, CLEAR_INTERVAL
        )

    async def _clear_diagnostics(self, now=None) -> None:
        """Clear diagnostics data after timeout if enabled."""
        if not self._enable_diagnostics:
            return
        self._diagnostics.update({"ssid": None, "rssi": None, "led": None})
        _LOGGER.debug("Cleared diagnostics for %s", self.sn)
        for name, entity in self._diagnostic_entities.items():
            if entity is not None:
                entity.schedule_update_ha_state()
                _LOGGER.debug(
                    "Directly updated diagnostic entity %s for %s", name, self.sn
                )

    async def _clear_notify(self, now=None) -> None:
        """Clear notify data after timeout."""
        self._data_dict.clear()
        _LOGGER.debug("Cleared notify data for %s", self.sn)
        for name, entity in self._entities.items():
            if entity is not None:
                entity.schedule_update_ha_state()
                _LOGGER.debug("Directly updated entity %s for %s", name, self.sn)

    async def handle_diagnostics(self, topic: str, payload: str) -> None:
        """Handle diagnostics JSON data from MQTT if enabled."""
        if not self._enable_diagnostics:
            return
        try:
            data = json.loads(payload)
            await self.update_diagnostics(data)
        except json.JSONDecodeError as e:
            _LOGGER.error("Invalid JSON payload for diagnostics %s: %s", self.sn, e)
        except (KeyError, TypeError, ValueError) as e:
            _LOGGER.error("Error handling diagnostics for %s: %s", self.sn, e)

    async def update_diagnostics(self, data: dict[str, any]) -> None:
        """Update diagnostics information from JSON data."""
        if not self._enable_diagnostics:
            return
        try:
            self._diagnostics.update(
                {
                    "ssid": data.get("ssid"),
                    "rssi": data.get("rssi"),
                    "led": data.get("led") == "on",
                }
            )
            _LOGGER.debug("Diagnostics updated for %s: %s", self.sn, self._diagnostics)
            self._reset_diagnostics_clear_timer()
            for sensor_name, entity in self._diagnostic_entities.items():
                if entity is not None:
                    entity.schedule_update_ha_state()
                    _LOGGER.debug(
                        "Directly updated diagnostic entity %s for %s",
                        sensor_name,
                        self.sn,
                    )
        except (KeyError, TypeError) as e:
            _LOGGER.error("Error in diagnostics data for device %s: %s", self.sn, e)

    def get_diagnostics(self) -> dict[str, any]:
        """Return diagnostics information if enabled."""
        return self._diagnostics.copy() if self._enable_diagnostics else {}

    def get_dict(self, name: str) -> any:
        """Return data for the given name from data_dict."""
        return self._data_dict.get(name)

    async def perform_action(self, action_name: str) -> None:
        """Perform an action based on the action name."""
        if action_name in {"restart", "reconfig"}:
            topic = self._build_topic("control", action_name)
            await self.mqtt_manager.publish(topic, action_name)

    async def set_led(self, state: bool) -> None:
        """Set LED state via MQTT if diagnostics enabled."""
        if not self._enable_diagnostics:
            return
        self._diagnostics["led"] = state
        try:
            topic = self._build_topic("control", "led")
            data = "on" if state else "off"
            await self.mqtt_manager.publish(topic, data)
            _LOGGER.debug("Published LED state %s to %s", state, topic)
            self._reset_diagnostics_clear_timer()
            for sensor_name, entity in self._diagnostic_entities.items():
                if entity is not None:
                    entity.schedule_update_ha_state()
                    _LOGGER.debug(
                        "Directly updated diagnostic entity %s for %s",
                        sensor_name,
                        self.sn,
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
            "button": [],
        }

        if self._enable_diagnostics:
            device_info["sensor"].extend(
                [
                    {"name": "SSID", "diagnostic": True, "icon": "mdi:wifi"},
                    {
                        "name": "RSSI",
                        "diagnostic": True,
                        "unit": "dBm",
                        "icon": "mdi:wifi-strength-2",
                    },
                ]
            )
            device_info["switch"].append(
                {"name": "LED", "diagnostic": True, "icon": "mdi:led-on"}
            )
            device_info["button"].extend(
                [
                    {"name": "restart", "diagnostic": True, "icon": "mdi:restart"},
                    {
                        "name": "reconfig",
                        "diagnostic": True,
                        "icon": "mdi:restore-alert",
                    },
                ]
            )

        return device_info

    @abstractmethod
    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle device-specific MQTT notifications (to be overridden by subclasses)."""

    @abstractmethod
    async def handle_cmd(self, cmd: str, value: any) -> None:
        """Handle commands from the user (to be overridden by subclasses)."""

    @abstractmethod
    def setup_protocol(self) -> None:
        """Set up device-specific protocol parameters."""

    def cleanup(self) -> None:
        """Cleanup device resources."""
        if self._enable_diagnostics:
            self.mqtt_manager.unregister_callback(self._build_topic("diagnostics"))
        self.mqtt_manager.unregister_callback(self._build_topic("notify"))
        self.mqtt_manager.unregister_callback(self._build_topic("online"))

        self._diagnostic_entities.clear()
        self._entities.clear()
        if self._diagnostics_clear_task:
            self._diagnostics_clear_task()
            self._diagnostics_clear_task = None
        if self._notify_clear_task:
            self._notify_clear_task()
            self._notify_clear_task = None
        self.parser = None
        self.mqtt_manager = None
        self.protocol_data = None
        self.hass = None
        self._data_dict.clear()
