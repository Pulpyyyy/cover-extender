"""Shared stateless helpers for cover_extender."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, translation as ha_translation

from .const import (
    DOMAIN,
    CONF_ENTITY_PICTURE,
    CONF_FACADE,
    CONF_MODES,
    CONF_SHADING,
    ATTR_FACADE,
    ATTR_MODES,
    ATTR_ENABLE_AUTO_SHADE,
)

_LOGGER = logging.getLogger(__name__)

_TITLE_FALLBACKS: dict[str, str] = {
    "global":         "General settings",
    "facade":         "Facades",
    "mode":           "Modes",
    "cover_template": "Templates",
    "cover":          "Covers",
}


async def _subentry_title(hass: HomeAssistant, subentry_type: str) -> str:
    """Return the translated entry_title for a singleton subentry."""
    try:
        translations = await ha_translation.async_get_translations(
            hass, hass.config.language, "config_subentries", {DOMAIN}
        )
        key = f"component.{DOMAIN}.config_subentries.{subentry_type}.entry_title"
        title = translations.get(key)
        if title:
            return title
    except Exception:
        pass
    return _TITLE_FALLBACKS.get(subentry_type, subentry_type)


# ── Helper entity resolution ──────────────────────────────────────────────────
# Helper entities (select.mode_*, switch.*_lock, …) are created with a
# deterministic unique_id derived from the cover's object id. Resolving their
# CURRENT entity_id through the registry (instead of rebuilding the
# conventional name) keeps the integration working when the user renames a
# helper entity in the UI. The conventional name remains as fallback for the
# window where an entity is not yet registered (fresh add before platform
# reload).

_HELPER_KINDS: dict[str, tuple[str, str, str]] = {
    # kind -> (domain, unique_id template, conventional entity_id template)
    "select_mode":     ("select", f"{DOMAIN}_select_mode_{{}}",            "select.mode_{}"),
    "lock":            ("switch", f"{DOMAIN}_switch_{{}}_lock",            "switch.{}_lock"),
    "auto_shade":      ("switch", f"{DOMAIN}_switch_{{}}_auto_shade",      "switch.{}_auto_shade"),
    "auto_solar_gain": ("switch", f"{DOMAIN}_switch_{{}}_auto_solar_gain", "switch.{}_auto_solar_gain"),
}


def cover_object_id(cover_entity_id: str) -> str:
    """Return the object id part of a cover entity id (cover.volet_sam → volet_sam)."""
    return cover_entity_id.split(".", 1)[1]


def resolve_helper_entity(hass: HomeAssistant, cover_entity_id: str, kind: str) -> str:
    """Return the current entity_id of a helper entity for *cover_entity_id*.

    Looks up the entity registry by unique_id (survives user renames) and falls
    back to the conventional entity_id when the entity is not registered yet.
    """
    name = cover_object_id(cover_entity_id)
    domain, uid_tpl, eid_tpl = _HELPER_KINDS[kind]
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, uid_tpl.format(name))
    return entity_id or eid_tpl.format(name)


def resolve_mode_position(hass: HomeAssistant, raw: Any) -> int | None:
    """Resolve a mode position value to an integer.

    - raw = None       → None (no fixed position, e.g. auto shade)
    - raw = int/float  → int
    - raw = str        → treated as entity_id; its numeric state is read at runtime
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        state = hass.states.get(raw)
        if state is None:
            _LOGGER.warning("cover_extender: position entity '%s' not found", raw)
            return None
        try:
            return int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "cover_extender: position entity '%s' has a non-numeric state: %s",
                raw, state.state,
            )
            return None
    return int(raw)


def build_extra_attrs(cfg: dict[str, Any], memory: int | None = None) -> dict[str, Any]:
    """Build the dict of extra attributes to inject into a cover entity."""
    attrs: dict[str, Any] = {}
    if entity_picture := cfg.get(CONF_ENTITY_PICTURE):
        attrs["entity_picture"] = entity_picture
    if facade := cfg.get(CONF_FACADE):
        attrs[ATTR_FACADE] = facade
    if modes := cfg.get(CONF_MODES):
        attrs[ATTR_MODES] = dict(modes)
    attrs[ATTR_ENABLE_AUTO_SHADE] = bool(cfg.get(CONF_SHADING, {}).get("enable", False))
    if memory is not None:
        attrs["memory"] = memory
    return attrs
