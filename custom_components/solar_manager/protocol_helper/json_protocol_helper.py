"""Generic JSON-over-MQTT protocol helper for Solar Manager.

Solar Manager or solar_manager © 2026 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.

This helper is intended for any device that exchanges JSON payloads
directly over MQTT (no Modbus framing, no HTTP transport). It provides
a generic ``parse_data`` for decoding inbound JSON bytes and a
callback-based ``write_data`` so plugins can route user-facing writes
through their own ``handle_cmd`` without going through a Modbus-shaped
``pack_data`` path.
"""

from __future__ import annotations

import json
from typing import Any

from custom_components.solar_manager.const import _LOGGER

from .protocol_helper import ProtocolHelper


class JsonProtocolHelper(ProtocolHelper):
    """Generic JSON-over-MQTT protocol helper.

    Unlike ``ModbusProtocolHelper`` this class does not carry any
    register addressing, CRC, or binary packing concerns. It deals in
    JSON objects in and out of the MQTT topics that the owning plugin
    subscribes to.
    """

    def register_callback(self, callback: callable) -> None:
        """Register the plugin callback invoked from ``write_data``.

        The callback receives ``(register_name, value)`` exactly like the
        Modbus helper so plugin code can use the same ``handle_cmd``
        signature regardless of transport.
        """
        self.callback = callback

    async def write_data(self, register_name: str, value: Any) -> None:
        """Route a user-facing write through the registered callback.

        JSON devices do not produce framed binary commands; the helper
        simply hands the ``(register_name, value)`` pair to the owning
        plugin, which composes and publishes the device-specific JSON
        payload itself.
        """
        if self.protocol_data is None:
            self.protocol_data = await self.load_protocol()

        _LOGGER.debug("JSON write_data: %s = %s", register_name, value)

        if self.callback is not None:
            await self.callback(register_name, value)

    def parse_data(self, data: bytes | str) -> dict[str, Any]:
        """Decode an inbound JSON payload into a dict.

        Returns an empty dict on malformed input or when the payload is
        not a JSON object. Errors are logged but never raised so one bad
        message cannot crash a notify handler.
        """
        try:
            decoded = json.loads(data)
        except (TypeError, ValueError) as err:
            _LOGGER.error("Invalid JSON payload: %s", err)
            return {}

        if not isinstance(decoded, dict):
            _LOGGER.error("JSON payload is not an object: %r", decoded)
            return {}

        return decoded
