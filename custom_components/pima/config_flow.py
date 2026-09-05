"""Config flow for PIMA Force."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_PORT

from .const import DEFAULT_PORT, DOMAIN

CONF_ACCOUNT = "account"


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the setup and reconfiguration schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ACCOUNT, default=defaults.get(CONF_ACCOUNT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required(
                CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")
            ): str,
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        }
    )


class PimaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle PIMA Force configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up PIMA Force from the UI."""
        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_ACCOUNT]))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="PIMA Force", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema())

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Import the existing YAML configuration once."""
        data = {
            CONF_ACCOUNT: int(import_data[CONF_ACCOUNT]),
            CONF_PASSWORD: str(import_data[CONF_PASSWORD]),
            CONF_PORT: int(import_data.get(CONF_PORT, DEFAULT_PORT)),
        }
        await self.async_set_unique_id(str(data[CONF_ACCOUNT]))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="PIMA Force", data=data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update account, password, or listener port."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_ACCOUNT]))
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(dict(entry.data)),
        )
