"""Config flow for the Solar Manager integration.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.mqtt import DOMAIN as MQTT_DOMAIN, MqttData
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import CONF_MODEL, CONF_SERIAL, CONF_SLAVE, DOMAIN
from .device_protocol.device_config import PROTOCOL_MAP, SUPPORTED_MODELS

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
    }
)

STEP_MODEL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODEL, default="MakeSkyBlue"): vol.In(SUPPORTED_MODELS),
    }
)

STEP_SETTINGS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SLAVE, default=15): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=255,
                step=1,
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)


class SolarManagerHub:
    """Class to manage the Solar Manager hub."""

    def __init__(self, serial: str) -> None:
        """Initialize the hub with the given serial number."""
        self.serial = serial

    async def authenticate(self, model: str) -> bool:
        """Test if we can authenticate with the serial and model."""
        return True


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    hub = SolarManagerHub(data[CONF_SERIAL])
    model = data[CONF_MODEL]

    if not await hub.authenticate(model):
        raise InvalidAuth

    return {"title": f"{model} ({data[CONF_SERIAL]})"}


async def check_mqtt_connection(hass: HomeAssistant | None) -> bool:
    """Check if the MQTT connection is active."""
    mqtt_data: MqttData = hass.data.get(MQTT_DOMAIN)

    if mqtt_data is None or mqtt_data.client is None or not mqtt_data.client.connected:
        return False
    return True


class SolarManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Manager."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._serial = None
        self._model = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Handle the serial number input."""
        errors: dict[str, str] = {}

        if not await check_mqtt_connection(self.hass):
            errors["base"] = "mqtt_not_ready"
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        if user_input is not None:
            self._serial = user_input[CONF_SERIAL]

            if any(
                entry.data[CONF_SERIAL] == self._serial
                for entry in self._async_current_entries()
            ):
                errors["base"] = "already_configured"
            else:
                return await self.async_step_model()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Handle the model selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._model = user_input[CONF_MODEL]

            if self._model == "JK BMS":
                return await self.async_step_settings()

            return await self._async_create_entry_helper(
                slave_id=None, error_step="model"
            )

        return self.async_show_form(
            step_id="model", data_schema=STEP_MODEL_DATA_SCHEMA, errors=errors
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Handle the Slave ID setting (Only for JK BMS)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            slave_id = user_input[CONF_SLAVE]
            return await self._async_create_entry_helper(
                slave_id=slave_id, error_step="settings"
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=STEP_SETTINGS_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"model": self._model},
        )

    async def _async_create_entry_helper(
        self, slave_id: int | None, error_step: str
    ) -> ConfigFlowResult:
        """Common helper to validate and create the entry."""
        errors: dict[str, str] = {}
        try:
            await validate_input(
                self.hass,
                {CONF_SERIAL: self._serial, CONF_MODEL: self._model},
            )

            protocol = PROTOCOL_MAP.get(self._model)
            if protocol is None:
                errors["base"] = "invalid_model"
            else:
                data = {
                    CONF_SERIAL: self._serial,
                    CONF_MODEL: self._model,
                }
                if slave_id is not None:
                    data[CONF_SLAVE] = slave_id

                return self.async_create_entry(
                    title=f"{self._model} ({self._serial})",
                    data=data,
                )
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # noqa: BLE001
            errors["base"] = "unknown"

        schema = (
            STEP_SETTINGS_DATA_SCHEMA
            if error_step == "settings"
            else STEP_MODEL_DATA_SCHEMA
        )
        return self.async_show_form(
            step_id=error_step, data_schema=schema, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
