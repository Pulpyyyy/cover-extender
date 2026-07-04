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


# ── Helper entity naming and resolution ──────────────────────────────────────
# Helper entities (select.mode_*, switch.*_lock, …) carry a deterministic
# unique_id. Since v2.2 the key inside the unique_id is the cover's entity
# REGISTRY id (immutable UUID) so that renaming the cover breaks nothing;
# covers without a registry entry (e.g. YAML template covers without
# unique_id) fall back to the object id, i.e. the pre-2.2 scheme. Legacy
# name-based unique_ids are migrated at setup (__init__._migrate_registry_ids)
# but every lookup still tries both schemes for robustness.

HELPER_UNIQUE_ID_TEMPLATES: dict[str, tuple[str, str]] = {
    # kind -> (domain, unique_id template — {} is the stable key)
    "select_mode":     ("select",        f"{DOMAIN}_select_mode_{{}}"),
    "lock":            ("switch",        f"{DOMAIN}_switch_{{}}_lock"),
    "auto_shade":      ("switch",        f"{DOMAIN}_switch_{{}}_auto_shade"),
    "auto_solar_gain": ("switch",        f"{DOMAIN}_switch_{{}}_auto_solar_gain"),
    "bs_sun_facing":   ("binary_sensor", f"{DOMAIN}_binary_sensor_{{}}_sun_facing"),
    "bs_auto_shade":   ("binary_sensor", f"{DOMAIN}_binary_sensor_{{}}_auto_shade"),
    "bs_solar_gain":   ("binary_sensor", f"{DOMAIN}_binary_sensor_{{}}_solar_gain"),
}

# Conventional entity_id suggested at creation (and used as last-resort
# fallback when the helper is not registered yet). Stays name-based on
# purpose: entity ids are human-facing.
_HELPER_CONVENTIONAL_EIDS: dict[str, str] = {
    "select_mode":     "select.mode_{}",
    "lock":            "switch.{}_lock",
    "auto_shade":      "switch.{}_auto_shade",
    "auto_solar_gain": "switch.{}_auto_solar_gain",
}


def cover_object_id(cover_entity_id: str) -> str:
    """Return the object id part of a cover entity id (cover.volet_sam → volet_sam)."""
    return cover_entity_id.split(".", 1)[1]


def cover_stable_key(hass: HomeAssistant, cover_entity_id: str) -> str:
    """Return the stable key for a cover: its registry id, else its object id."""
    reg = er.async_get(hass).async_get(cover_entity_id)
    return reg.id if reg else cover_object_id(cover_entity_id)


def helper_unique_id(kind: str, stable_key: str) -> str:
    """Build the unique_id of a helper entity from its kind and stable key."""
    return HELPER_UNIQUE_ID_TEMPLATES[kind][1].format(stable_key)


def _lookup_helper(hass: HomeAssistant, cover_entity_id: str, kind: str) -> str | None:
    """Registry lookup of a helper entity, trying the registry-id scheme then
    the legacy name-based scheme. Returns None when not registered."""
    domain, uid_tpl = HELPER_UNIQUE_ID_TEMPLATES[kind]
    registry = er.async_get(hass)
    for key in dict.fromkeys(
        (cover_stable_key(hass, cover_entity_id), cover_object_id(cover_entity_id))
    ):
        entity_id = registry.async_get_entity_id(domain, DOMAIN, uid_tpl.format(key))
        if entity_id:
            return entity_id
    return None


def resolve_helper_entity(hass: HomeAssistant, cover_entity_id: str, kind: str) -> str:
    """Return the current entity_id of a helper entity for *cover_entity_id*.

    Registry lookup by unique_id (survives renames of both the helper and the
    cover), falling back to the conventional entity_id when the entity is not
    registered yet (fresh add before platform reload).
    """
    return (
        _lookup_helper(hass, cover_entity_id, kind)
        or _HELPER_CONVENTIONAL_EIDS[kind].format(cover_object_id(cover_entity_id))
    )


def purge_helper_entity(hass: HomeAssistant, cover_entity_id: str, kind: str) -> None:
    """Remove a helper entity from the registry (both unique_id schemes)."""
    entity_id = _lookup_helper(hass, cover_entity_id, kind)
    if entity_id:
        er.async_get(hass).async_remove(entity_id)


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
