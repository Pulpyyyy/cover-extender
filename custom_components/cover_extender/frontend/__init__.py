"""Registration of the hidden admin panel.

Same delivery principle as an embedded Lovelace card (the JS travels inside
the integration, served from a static path with a ?v= cache-buster), but the
UI here is a *panel*, not a card — so no Lovelace resource is involved at all.

The panel declares a sidebar_title, which is what puts it in the sidebar AND —
the actual reason — what makes it appear in Home Assistant's own sidebar editor
(long-press the sidebar header). A panel without a title is not merely hidden:
it cannot be shown by anyone. Declaring the title is therefore what turns the
sidebar entry into a per-USER choice, stored in each user's frontend settings,
rather than an integration-wide one we would have to persist and re-apply.

Other ways in, unchanged:
  - the hub device's configuration_url  (Settings → Devices → Cover Extender)
  - the direct URL                       http://ha:8123/cover-extender
It is admin-only: the panel writes the integration's configuration.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from ..const import (
    ADMIN_JS,
    DOMAIN,
    FALLBACK_VERSION,
    PANEL_NAME,
    PANEL_SIDEBAR_ICON,
    PANEL_SIDEBAR_TITLE,
    PANEL_URL_PATH,
    URL_BASE,
)

_LOGGER = logging.getLogger(__name__)


async def async_register(hass: HomeAssistant) -> None:
    """Serve the admin JS and (re-)register the hidden panel."""
    # Static path: the file only, never the folder — a static path is served
    # without authentication and the package must not travel with it.
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                f"{URL_BASE}/{ADMIN_JS}",
                str(Path(__file__).parent / ADMIN_JS),
                True,
            )
        ])
        _LOGGER.debug("frontend: static path registered (%s)", URL_BASE)
    except (RuntimeError, ValueError):
        _LOGGER.debug("frontend: static path already registered (%s)", URL_BASE)

    # ?v= comes from the manifest, as HA already parsed it: it is what makes
    # an upgrade visible to a browser holding the old module in cache.
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version or FALLBACK_VERSION)
    except Exception:  # noqa: BLE001
        version = FALLBACK_VERSION

    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        frontend_url_path=PANEL_URL_PATH,
        sidebar_title=PANEL_SIDEBAR_TITLE,
        sidebar_icon=PANEL_SIDEBAR_ICON,
        require_admin=True,
        config={
            "_panel_custom": {
                "name": PANEL_NAME,
                "module_url": f"{URL_BASE}/{ADMIN_JS}?v={version}",
                "embed_iframe": False,
                "trust_external": False,
            }
        },
        update=True,  # idempotent across entry reloads
    )
    _LOGGER.debug("frontend: panel registered at /%s (v%s)", PANEL_URL_PATH, version)


def async_unregister(hass: HomeAssistant) -> None:
    """Remove the panel when the integration is deleted."""
    try:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    except Exception:  # noqa: BLE001 — panel already gone is fine
        pass
