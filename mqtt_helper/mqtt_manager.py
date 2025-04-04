"""MQTT Manager for handling MQTT connections and message processing."""

import asyncio
import json
import logging
import threading
import time

import paho.mqtt.client as mqtt

from .singleton_meta import SingletonMeta

_LOGGER = logging.getLogger(__name__)


class MQTTManager(metaclass=SingletonMeta):
    """Manage MQTT connections and message handling."""

    def __init__(
        self,
        broker: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the MQTTManager.

        Args:
            broker (str): The MQTT broker address.
            port (int): The port to connect to the MQTT broker.
            username (str, optional): Username for MQTT authentication.
            password (str, optional): Password for MQTT authentication.

        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password

        self.client = mqtt.Client()
        if username and password:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.loop = asyncio.new_event_loop()
        self._event_thread = threading.Thread(
            target=self._start_event_loop, daemon=True
        )
        self._event_thread.start()

        self._loop_thread = threading.Thread(target=self._start_loop, daemon=True)
        self._loop_thread.start()

        # 用于存储每个设备的回调函数
        self.callbacks = {}

    def _start_event_loop(self):
        asyncio.set_event_loop(self.loop)
        _LOGGER.info(
            "Asyncio event loop started in thread: %s", threading.current_thread().name
        )
        self.loop.run_forever()

    def _start_loop(self):
        _LOGGER.info("Starting MQTT loop")
        asyncio.set_event_loop(self.loop)
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_forever()

    def on_connect(self, client, userdata, flags, rc):
        """Handle connection to the MQTT broker.

        Args:
            client: The MQTT client instance.
            userdata: The private user data as set in Client().
            flags: Response flags sent by the broker.
            rc: The connection result code.

        """
        _LOGGER.info("Connected to MQTT broker with result code %s", rc)
        client.subscribe("notify/#")

    def on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages.

        Args:
            client: The MQTT client instance.
            userdata: The private user data as set in Client().
            msg: The MQTT message containing topic and payload.

        """
        try:
            for topic_prefix, callback in self.callbacks.items():
                if msg.topic.startswith(topic_prefix):
                    asyncio.run_coroutine_threadsafe(
                        callback(msg.topic, msg.payload), self.loop
                    )
        except (ValueError, TypeError) as e:
            _LOGGER.error("Failed to handle MQTT message due to invalid data: %s", e)
        except RuntimeError as e:
            _LOGGER.error("Failed to handle MQTT message due to runtime error: %s", e)

    def on_disconnect(self, client, userdata, rc):
        """Handle disconnection from the MQTT broker.

        Args:
            client: The MQTT client instance.
            userdata: The private user data as set in Client().
            rc: The disconnection result code.

        """
        _LOGGER.warning("Disconnected from MQTT broker, reconnecting in 5 seconds")
        time.sleep(5)
        self.client.reconnect()

    def register_callback(self, topic_prefix: str, callback: callable) -> None:
        """Register a callback function for a specific topic prefix.

        Args:
            topic_prefix (str): The topic prefix to listen for.
            callback (callable): The callback function to handle messages.

        """
        self.client.subscribe(topic_prefix + "/#")
        self.callbacks[topic_prefix] = callback

    def publish(self, topic: str, payload: bytes | dict | str) -> None:
        """Publish a message to a specific MQTT topic.

        Args:
            topic (str): The MQTT topic to publish the message to.
            payload (Union[bytes, dict]): The message payload to publish.
                Can be bytes or a dictionary.

        """
        if isinstance(payload, bytes):
            self.client.publish(topic, payload)
        elif isinstance(payload, dict):
            self.client.publish(topic, json.dumps(payload).encode("utf-8"))
        elif isinstance(payload, str):
            self.client.publish(topic, payload.encode("utf-8"))
        else:
            _LOGGER.error("Unsupported payload type: %s", type(payload))
