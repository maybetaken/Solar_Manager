"""Switches device class for Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from custom_components.solar_manager.const import DOMAIN
from custom_components.solar_manager.protocol_helper.json_protocol_helper import (
    JsonProtocolHelper,
)

from homeassistant.core import HomeAssistant

from .base_device import BaseDevice

_LOGGER = logging.getLogger(__name__)


class SwitchesDevice(BaseDevice):
    """Switches device class for Solar Manager integration.

    A logical multi-switch controller that exposes two or more binary
    on/off switch entities. Serial numbers ending with ``-K`` identify
    attached (sub-module) variants that share another device's network
    connection and therefore SHALL NOT expose network diagnostic
    entities or maintenance buttons.
    """

    MIN_SWITCH_COUNT = 2
    ATTACHED_SUFFIX = "-K"
    MAX_PAYLOAD_PREVIEW = 64

    def __init__(
        self, hass: HomeAssistant, protocol_file: str, sn: str, model: str
    ) -> None:
        """Initialize the Switches device.

        Classifies the device as attached or standalone based on the
        serial number suffix BEFORE delegating to ``BaseDevice.__init__``
        so that ``enable_diagnostics`` can be flipped for attached
        sub-modules.
        """
        is_attached = sn.endswith(self.ATTACHED_SUFFIX)
        super().__init__(
            hass,
            protocol_file,
            sn,
            model,
            enable_diagnostics=not is_attached,
        )
        self._is_attached = is_attached
        self._switch_count = self.MIN_SWITCH_COUNT
        self._add_entities_cb: Optional[Callable[[list[Any]], Any]] = None
        self._pending_target_count: Optional[int] = None
        self.parser = JsonProtocolHelper(hass, protocol_file)
        self.setup_protocol()

    @staticmethod
    def switch_name(index_one_based: int) -> str:
        """Return the canonical translation-key name for a switch index.

        Indices are one-based and zero-padded to at least two digits, so
        the first switch is ``switch_01``, the tenth is ``switch_10``,
        and the sixteenth is ``switch_16``.
        """
        return f"switch_{index_one_based:02d}"

    def setup_protocol(self) -> None:
        """Set up device-specific protocol parameters.

        Switches use JSON-over-MQTT commands rather than Modbus register
        polling. The protocol helper still routes user-facing writes
        through ``handle_cmd`` so the command payload is published on
        ``{serial}/control/cmd``.
        """
        self.parser.register_callback(self.handle_cmd)

    async def send_config(self) -> None:
        """Publish an empty JSON config for parity with other plugins.

        Switches does not carry Modbus segments, so the config payload is
        an empty JSON object. Emitting the topic keeps the firmware side
        compatible with the existing "HA sent config" handshake.
        """
        try:
            await self.mqtt_manager.publish(
                self._build_topic("config"), json.dumps({})
            )
        except Exception as err:  # noqa: BLE001 - mirror other plugins' broad guard
            _LOGGER.error("Config send failed for %s: %s", self.sn, err)

    def set_add_entities_callback(
        self, cb: Callable[[list[Any]], Any]
    ) -> None:
        """Store the platform's ``async_add_entities`` callback.

        Captured by ``switch.py`` so that later online-payload-driven
        growth in ``handle_online`` can add switch entities dynamically.
        If an online payload arrived before the callback was registered,
        the deferred target count is applied now.
        """
        self._add_entities_cb = cb
        pending = self._pending_target_count
        if pending is not None and pending > self._switch_count:
            self._pending_target_count = None
            self.hass.async_create_task(self._reconcile_to(pending))

    async def unpack_device_info(self) -> dict[str, list[dict[str, Any]]]:
        """Unpack device information into platform entity groups.

        Delegates to ``BaseDevice.unpack_device_info`` first so that
        diagnostic sensors (SSID, RSSI), the LED diagnostic switch, and
        the Restart/Reconfig maintenance buttons are emitted automatically
        for standalone devices and skipped for attached (``-K``) devices.

        Two default ``switch_01`` and ``switch_02`` entries are always
        appended. The switch count may grow later when the device
        publishes its ``switch_count`` on the ``online`` topic; those
        additional entities are added dynamically via the stored
        ``async_add_entities`` callback.
        """
        device_info = super().unpack_device_info()

        # Reset to the initial default count; later online payloads may
        # grow (or shrink) the exposed set.
        self._switch_count = self.MIN_SWITCH_COUNT
        for index in range(1, self.MIN_SWITCH_COUNT + 1):
            name = self.switch_name(index)
            device_info["switch"].append(
                {
                    "name": name,
                    "device": self,
                    "register": index,
                    "icon": "mdi:toggle-switch",
                }
            )

        return device_info

    async def handle_online(self, topic: str, payload: bytes) -> None:
        """Handle ``{serial}/online`` messages and reconcile entities.

        Parses the JSON payload, validates a strict ``switch_count``
        integer field, and reconciles the exposed switch entity set to
        match. Invalid or malformed payloads log an error, leave the
        prior count untouched, and still trigger the base-class
        ``send_config`` behavior so the device side-effects are
        preserved.
        """
        target = self._parse_switch_count(payload)
        if target is not None:
            await self._reconcile_to(target)

        # Preserve BaseDevice.handle_online side-effects (log + send_config).
        await super().handle_online(topic, payload)

    def _parse_switch_count(self, payload: bytes) -> Optional[int]:
        """Validate the ``online`` payload and return a clean switch count.

        Returns the integer ``switch_count`` if the payload is a JSON
        object containing a real integer ``>= MIN_SWITCH_COUNT``. On any
        failure (invalid JSON, non-dict, missing field, wrong type,
        ``bool``, ``float``, or value below the minimum) logs an error
        and returns ``None`` so callers keep the previous count.
        """
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as err:
            _LOGGER.error(
                "Invalid JSON on online topic for %s: %s (payload preview=%r)",
                self.sn,
                err,
                self._payload_preview(payload),
            )
            return None

        if not isinstance(decoded, dict):
            _LOGGER.error(
                "Online payload for %s is not a JSON object: %r",
                self.sn,
                decoded,
            )
            return None

        if "switch_count" not in decoded:
            _LOGGER.error(
                "Online payload for %s missing 'switch_count' field: %r",
                self.sn,
                decoded,
            )
            return None

        value = decoded["switch_count"]
        # ``bool`` is a subclass of ``int`` — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int):
            _LOGGER.error(
                "Online 'switch_count' for %s is not an int: %r",
                self.sn,
                value,
            )
            return None

        if value < self.MIN_SWITCH_COUNT:
            _LOGGER.error(
                "Online 'switch_count'=%d for %s is below minimum %d",
                value,
                self.sn,
                self.MIN_SWITCH_COUNT,
            )
            return None

        return value

    @staticmethod
    def _payload_preview(payload: bytes) -> str:
        """Return a safe preview of an MQTT payload for logging."""
        try:
            text = payload.decode("utf-8", errors="replace")
        except AttributeError:
            text = str(payload)
        if len(text) > SwitchesDevice.MAX_PAYLOAD_PREVIEW:
            return text[: SwitchesDevice.MAX_PAYLOAD_PREVIEW] + "…"
        return text

    async def _reconcile_to(self, target_count: int) -> None:
        """Reconcile the exposed entity set to ``target_count``.

        Grow path: if more entities are needed, create new
        ``SolarManagerSwitch`` instances and hand them to the platform's
        stored ``async_add_entities`` callback. If the callback is not
        yet registered (startup race), buffer the target so
        ``set_add_entities_callback`` can complete the growth once it is
        captured.

        Shrink path: entity objects are NOT removed. Their data-dict
        entries are cleared so ``SolarManagerSwitch.available`` reports
        ``False``. Automations relying on those entity ids therefore do
        not break mid-session.
        """
        if target_count == self._switch_count:
            return

        if target_count > self._switch_count:
            await self._grow_to(target_count)
        else:
            self._shrink_to(target_count)

    async def _grow_to(self, target_count: int) -> None:
        """Add missing switch entities up to ``target_count``."""
        # Imported lazily to avoid a circular import between the plugin
        # and the switch platform.
        from custom_components.solar_manager.switch import SolarManagerSwitch

        if self._add_entities_cb is None:
            prior = self._pending_target_count or target_count
            self._pending_target_count = max(prior, target_count)
            _LOGGER.debug(
                "Deferring switch growth for %s: target=%d (callback not yet set)",
                self.sn,
                self._pending_target_count,
            )
            return

        new_entities: list[SolarManagerSwitch] = []
        for index in range(self._switch_count + 1, target_count + 1):
            name = self.switch_name(index)
            unique_id = f"{name}_{self.model}_{self.sn}"
            entity = SolarManagerSwitch(
                name=name,
                model=self.model,
                device=self,
                register=index,
                unique_id=unique_id,
                device_id=self.sn,
                icon="mdi:toggle-switch",
            )
            new_entities.append(entity)

        if new_entities:
            self._add_entities_cb(new_entities)

        self._switch_count = target_count

    def _shrink_to(self, target_count: int) -> None:
        """Mark excess switch entities unavailable without removing them."""
        for index in range(target_count + 1, self._switch_count + 1):
            name = self.switch_name(index)
            self._data_dict[name] = None
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()

        self._switch_count = target_count

    async def handle_notify(self, topic: str, payload: bytes) -> None:
        """Handle ``{serial}/notify`` state reports from the device.

        Expected payload: a JSON object mapping switch names to states,
        e.g. ``{"switch_01": "on", "switch_03": "off"}``. Parsing is
        delegated to ``self.parser.parse_data`` so the JSON decoding
        logic lives in the shared ``JsonProtocolHelper``.
        """
        decoded = self.parser.parse_data(payload)
        if not decoded:
            return

        changed: list[str] = []
        for key, state in decoded.items():
            index = self._parse_switch_key(key)
            if index is None:
                _LOGGER.warning(
                    "Skipping unknown notify key for %s: %r", self.sn, key
                )
                continue

            if index < 1 or index > self._switch_count:
                _LOGGER.warning(
                    "Ignoring notify key %r outside [1, %d] for %s",
                    key,
                    self._switch_count,
                    self.sn,
                )
                continue

            if state not in ("on", "off"):
                _LOGGER.warning(
                    "Skipping notify entry %r with invalid state for %s: %r",
                    key,
                    self.sn,
                    state,
                )
                continue

            name = self.switch_name(index)
            value = 1 if state == "on" else 0
            if self._data_dict.get(name) != value:
                self._data_dict[name] = value
                changed.append(name)

        for name in changed:
            entity = self._entities.get(name)
            if entity is not None:
                entity.schedule_update_ha_state()

        self._reset_notify_clear_timer()

    @staticmethod
    def _parse_switch_key(key: Any) -> Optional[int]:
        """Extract a one-based switch index from a ``switch_NN`` key.

        Returns ``None`` if the key is not a ``switch_`` prefixed string
        or if the trailing portion is not a positive integer.
        """
        if not isinstance(key, str) or not key.startswith("switch_"):
            return None
        try:
            index = int(key[len("switch_") :])
        except ValueError:
            return None
        if index < 1:
            return None
        return index

    async def handle_cmd(self, cmd: Any, value: Any) -> None:
        """Publish a switch command to ``{serial}/control/cmd``.

        Accepts ``cmd`` as the one-based switch index and ``value`` as a
        truthy/falsy-convertible value. Validates the index is within
        ``[1, _switch_count]`` and logs a clear error if not, never
        publishing an invalid command onto the wire. The published
        payload is a JSON object keyed by the canonical switch name,
        e.g. ``{"switch_03": "on"}``.
        """
        try:
            index = int(cmd)
        except (TypeError, ValueError):
            _LOGGER.error(
                "Switch command index for %s is not an int: %r", self.sn, cmd
            )
            return

        if index < 1 or index > self._switch_count:
            _LOGGER.error(
                "Switch command index %d out of range [1, %d] for %s",
                index,
                self._switch_count,
                self.sn,
            )
            return

        try:
            bool_value = bool(int(float(value)))
        except (TypeError, ValueError):
            _LOGGER.error(
                "Switch command value for %s index %d is not a boolean: %r",
                self.sn,
                index,
                value,
            )
            return

        name = self.switch_name(index)
        payload = json.dumps({name: "on" if bool_value else "off"})
        try:
            await self.mqtt_manager.publish(self.cmd_topic, payload)
        except Exception as err:  # noqa: BLE001 - mirror other plugins' broad guard
            _LOGGER.error(
                "Failed to publish switch command for %s index %d: %s",
                self.sn,
                index,
                err,
            )
