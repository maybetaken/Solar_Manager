import asyncio
import json
import logging
import struct
import threading
import time

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)


class MQTTManager:
    """Manage MQTT connections and message handling."""

    def __init__(self, hass, broker, port, callback=None, username=None, password=None):
        self.hass = hass
        self.broker = broker
        self.port = port
        self.callback = callback
        self.username = username
        self.password = password

        self.client = mqtt.Client()
        if username and password:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        # 启动MQTT事件循环
        self._loop_thread = threading.Thread(target=self._start_loop, daemon=True)
        self._loop_thread.start()

    def _start_loop(self):
        _LOGGER.info("Starting MQTT loop...")
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_forever()

    def on_connect(self, client, userdata, flags, rc):
        _LOGGER.info("Connected to MQTT broker with result code %s", rc)
        client.subscribe("/notify/#")

    def on_message(self, client, userdata, msg):
        _LOGGER.info("MQTT message received on topic %s: %s", msg.topic, msg.payload)
        try:
            if self.callback:
                # 将原始的 bytes 数据传递给回调
                asyncio.run_coroutine_threadsafe(
                    self.callback(msg.topic, msg.payload), self.hass.loop
                )
        except Exception as e:
            _LOGGER.error("Failed to handle MQTT message: %s", e)

    def on_disconnect(self, client, userdata, rc):
        _LOGGER.warning("Disconnected from MQTT broker, reconnecting in 5 seconds...")
        time.sleep(5)
        self.client.reconnect()

    def publish(self, topic, payload):
        if isinstance(payload, bytes):
            self.client.publish(topic, payload)
        elif isinstance(payload, dict):
            self.client.publish(topic, json.dumps(payload).encode("utf-8"))
        else:
            _LOGGER.error("Unsupported payload type: %s", type(payload))
