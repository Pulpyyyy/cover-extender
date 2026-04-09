"""Config flow for Cover Extender."""
from __future__ import annotations

import pathlib

import voluptuous as vol
import yaml
from homeassistant import config_entries

from .const import DOMAIN, CONF_SOURCE

_STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_SOURCE): str,
})


def _validate_source(config_dir: str, source: str) -> str | None:
    """Validate source path and YAML content (runs in executor). Returns error key or None."""
    config_root = pathlib.Path(config_dir).resolve()

    if pathlib.Path(source).is_absolute():
        resolved = pathlib.Path(source).resolve()
    else:
        # Restrict relative paths to the HA config directory to prevent traversal attacks
        resolved = (config_root / source).resolve()
        try:
            resolved.relative_to(config_root)
        except ValueError:
            return "path_outside_config"

    if not resolved.is_file():
        return "file_not_found"

    try:
        with open(resolved, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return "yaml_invalid"

    if not any(isinstance(k, str) and k.startswith("cover.") for k in raw):
        return "no_covers_found"

    return None


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
            error = await self.hass.async_add_executor_job(
                _validate_source, self.hass.config.config_dir, source
            )
            if error:
                errors[CONF_SOURCE] = error
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
