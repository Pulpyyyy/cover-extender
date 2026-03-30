"""Config flow for Cover Extender."""
from __future__ import annotations

import os

import voluptuous as vol
import yaml
from homeassistant import config_entries

from .const import DOMAIN, CONF_SOURCE

_STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_SOURCE): str,
})


class CoverExtenderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Extender."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            source: str = user_input[CONF_SOURCE]
            path = source if os.path.isabs(source) else self.hass.config.path(source)
            if not os.path.isfile(path):
                errors[CONF_SOURCE] = "file_not_found"
            else:
                try:
                    with open(path, encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                except yaml.YAMLError:
                    errors[CONF_SOURCE] = "yaml_invalid"
                else:
                    if not any(isinstance(k, str) and k.startswith("cover.") for k in raw):
                        errors[CONF_SOURCE] = "no_covers_found"
                    else:
                        await self.async_set_unique_id(DOMAIN)
                        self._abort_if_unique_id_configured(updates=user_input)
                        return self.async_create_entry(title="Cover Extender", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_import(
        self, import_config: dict
    ) -> config_entries.ConfigFlowResult:
        """Import from configuration.yaml (backward compat)."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates=import_config)
        return self.async_create_entry(title="Cover Extender", data=import_config)
