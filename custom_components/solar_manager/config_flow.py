"""Config flow for the Solar Manager integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_MODEL, CONF_SERIAL, DOMAIN
from .device_protocol.protocol_map import protocol_map

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_MODEL): str,
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
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    hub = SolarManagerHub(data[CONF_SERIAL])

    if not await hub.authenticate(data[CONF_MODEL]):
        raise InvalidAuth

    name = f"{data[CONF_MODEL]} ({data[CONF_SERIAL]})"

    return {"title": name}


class SolarManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Check if the serial already exists
            if any(
                entry.data[CONF_SERIAL] == user_input[CONF_SERIAL]
                for entry in self._async_current_entries()
            ):
                errors["base"] = "already_configured"
            else:
                try:
                    info = await validate_input(self.hass, user_input)
                    model = user_input[CONF_MODEL]
                    protocol = protocol_map.get(model)
                    if protocol is None:
                        errors["base"] = "invalid_model"
                    else:
                        return self.async_create_entry(
                            title=info["title"], data=user_input
                        )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
