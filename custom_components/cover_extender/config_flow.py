"""Config flow for Cover Extender.

Deliberately minimal. Creating the config entry is all this flow still does:
facades, modes, templates, covers and the global settings are edited in the
admin panel served at ``/cover-extender`` (see ``frontend/`` and
``websocket_api.py``), which writes the very same entry options the
coordinator reads.

The subentry wizards that used to live here — 42 ``async_step_*`` spread over
five ``ConfigSubentryFlow`` classes — were removed once the panel covered every
operation they offered (create, edit, delete, rename cascade, per-cover mode
positions). The subentries they wrote outlived them as pure storage until v2.7,
when ``async_migrate_entry`` lifted their contents into ``entry.options`` and
deleted them: with no wizard and no device attached, all they still did was put
five empty groups on the integration page.

One subentry type is still declared, and it is not a subentry at all:
``EditorLinkFlowHandler`` aborts on its first step and stores nothing. Declaring
a type is the only hook Home Assistant offers for putting a button at the top of
the integration page, and that button is what carries the link to the panel —
otherwise the sole route in is the hub device's configuration URL, two clicks
deep and impossible to guess.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigSubentryFlow, SubentryFlowResult
from homeassistant.core import callback

from .const import DOMAIN, PANEL_URL_PATH, SUBENTRY_TYPE_EDITOR

_LOGGER = logging.getLogger(__name__)


class EditorLinkFlowHandler(ConfigSubentryFlow):
    """A button, not a wizard: shows the link to the admin panel and stops.

    Never calls async_create_entry, so no subentry of this type can ever exist.
    """

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        _LOGGER.debug("config_flow: pointing the user at /%s", PANEL_URL_PATH)
        return self.async_abort(
            reason="open_editor",
            description_placeholders={"url": f"/{PANEL_URL_PATH}"},
        )


class CoverExtenderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Extender."""

    # v2: the five configuration sections moved from singleton config subentries
    # into entry.options (see __init__.async_migrate_entry).
    VERSION = 2

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_TYPE_EDITOR: EditorLinkFlowHandler}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        # Single instance is enforced by "single_config_entry" in manifest.json
        _LOGGER.debug("config_flow: creating the Cover Extender entry")
        return self.async_create_entry(title="Cover Extender", data={})
