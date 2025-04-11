"""Helper module for managing MQTT communication in Home Assistant."""

import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.mqtt import ReceiveMessage
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class MQTTManager:
    """Class to manage MQTT communication."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the MQTTManager with the Home Assistant instance.

        Args:
            hass (HomeAssistant): The Home Assistant instance.

        """
        self.hass = hass
        self._callbacks = {}  # topic_prefix -> (unsubscribe func, callback)

    async def publish(self, topic: str, payload) -> None:
        """Publish message to topic."""
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            payload = payload.encode("utf-8")

        await mqtt.async_publish(self.hass, topic, payload)

    async def register_callback(self, topic_prefix: str, callback):
        """Subscribe to a topic prefix and register callback."""

        async def wrapped_callback(msg: ReceiveMessage):
            try:
                await callback(msg.topic, msg.payload)
            except Exception as e:
                _LOGGER.exception("Callback error on topic %s: %s", msg.topic, e)

        topic_filter = topic_prefix.rstrip("/") + "/#"
        unsubscribe = await mqtt.async_subscribe(
            self.hass, topic_filter, wrapped_callback, qos=0, encoding=None
        )
        self._callbacks[topic_prefix] = (unsubscribe, wrapped_callback)
        _LOGGER.info("Subscribed to %s", topic_filter)

    def unregister_callback(self, topic_prefix: str):
        """Unsubscribe from topic."""
        if topic_prefix in self._callbacks:
            unsubscribe, _ = self._callbacks.pop(topic_prefix)
            unsubscribe()
            _LOGGER.info("Unsubscribed from %s/#", topic_prefix)
