"""Config flow for the Solar Manager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.mqtt import DOMAIN as MQTT_DOMAIN, MqttData
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .device_protocol.protocol_map import protocol_map

SUPPORTED_MODELS = ["MakeSkyBlue", "ChintMeter"]

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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if not await check_mqtt_connection(self.hass):
            errors["base"] = "mqtt_not_ready"
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        if user_input is not None:
            self._serial = user_input[CONF_SERIAL]

            # Check if serial already exists
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
        """Handle the model selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                model = user_input[CONF_MODEL]
                await validate_input(
                    self.hass,
                    {CONF_SERIAL: self._serial, CONF_MODEL: model},
                )
                protocol = protocol_map.get(model)
                if protocol is None:
                    errors["base"] = "invalid_model"
                else:
                    return self.async_create_entry(
                        title=f"{model} ({self._serial})",
                        data={
                            CONF_SERIAL: self._serial,
                            CONF_MODEL: model,
                        },
                    )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="model", data_schema=STEP_MODEL_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
