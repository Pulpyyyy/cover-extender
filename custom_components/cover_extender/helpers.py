"""Shared stateless helpers for cover_extender."""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
# purpose: entity ids are human-facing. Since 4.0 they read
# <domain>.<cover>_cx_<function>: the cover first, so a helper sorts next to
# its cover, then "cx", so every id says which integration made it.
_HELPER_CONVENTIONAL_EIDS: dict[str, str] = {
    "select_mode":     "select.{}_cx_mode",
    "lock":            "switch.{}_cx_lock",
    "auto_shade":      "switch.{}_cx_auto_shade",
    "auto_solar_gain": "switch.{}_cx_auto_solar_gain",
    "bs_sun_facing":   "binary_sensor.{}_cx_sun_facing",
    "bs_auto_shade":   "binary_sensor.{}_cx_auto_shade_status",
    "bs_solar_gain":   "binary_sensor.{}_cx_solar_gain_status",
}

# Display names. Fixed English on purpose, never translated: a name that
# changed with the reader's language would make every log, screenshot and
# forum report read differently. The leading "CX" also keeps Home Assistant's
# own "rename the entity ids with the device" suggestion on the cx scheme,
# since it derives the ids from <device name> <entity name>.
HELPER_NAMES: dict[str, str] = {
    "select_mode":     "CX mode",
    "lock":            "CX lock",
    "auto_shade":      "CX auto shade",
    "auto_solar_gain": "CX auto solar gain",
    "bs_sun_facing":   "CX sun facing",
    "bs_auto_shade":   "CX auto shade status",
    "bs_solar_gain":   "CX solar gain status",
}

# The one helper that belongs to no cover.
GLOBAL_SELECT_UNIQUE_ID = f"{DOMAIN}_select_cover_extender_modes"
GLOBAL_SELECT_ENTITY_ID = "select.cx_modes"
GLOBAL_SELECT_NAME = "Modes"

# Ids before 4.0, per kind: the regex captures the cover part, kept as is.
_LEGACY_EID_PATTERNS: dict[str, re.Pattern[str]] = {
    "select_mode":     re.compile(r"^select\.mode_(.+)$"),
    "lock":            re.compile(r"^switch\.(.+)_lock$"),
    "auto_shade":      re.compile(r"^switch\.(.+)_auto_shade$"),
    "auto_solar_gain": re.compile(r"^switch\.(.+)_auto_solar_gain$"),
    "bs_sun_facing":   re.compile(r"^binary_sensor\.(.+)_sun_facing$"),
    "bs_auto_shade":   re.compile(r"^binary_sensor\.(.+)_auto_shade$"),
    "bs_solar_gain":   re.compile(r"^binary_sensor\.(.+)_solar_gain$"),
}
_LEGACY_GLOBAL_SELECT_ENTITY_ID = "select.cover_extender_modes"


def cover_object_id(cover_entity_id: str) -> str:
    """Return the object id part of a cover entity id (cover.volet_sam → volet_sam)."""
    return cover_entity_id.split(".", 1)[1]


def helper_entity_id(kind: str, cover_entity_id: str) -> str:
    """Conventional entity_id of a helper (cover.volet_sam, lock → switch.volet_sam_cx_lock)."""
    return _HELPER_CONVENTIONAL_EIDS[kind].format(cover_object_id(cover_entity_id))


def helper_kind(domain: str, unique_id: str) -> str | None:
    """Which helper a registry entry is, read off its unique_id (None: not a cover helper)."""
    for kind, (kind_domain, uid_tpl) in HELPER_UNIQUE_ID_TEMPLATES.items():
        prefix, _, suffix = uid_tpl.partition("{}")
        if (
            domain == kind_domain
            and unique_id.startswith(prefix)
            and unique_id.endswith(suffix)
            and len(unique_id) > len(prefix) + len(suffix)
        ):
            return kind
    return None


def v4_entity_id(domain: str, unique_id: str, entity_id: str) -> str | None:
    """The 4.0 entity_id for a helper still carrying its pre-4.0 id, else None.

    Only an id that still has the pre-4.0 SHAPE is renamed; the cover part is
    kept as it is (it may be an old cover name, a _2 suffix, a name the user
    chose). An id the user rewrote in any other way is theirs and stays.
    """
    if unique_id == GLOBAL_SELECT_UNIQUE_ID:
        return GLOBAL_SELECT_ENTITY_ID if entity_id == _LEGACY_GLOBAL_SELECT_ENTITY_ID else None
    kind = helper_kind(domain, unique_id)
    if kind is None:
        return None
    match = _LEGACY_EID_PATTERNS[kind].match(entity_id)
    if match is None or "_cx_" in entity_id:
        return None
    return _HELPER_CONVENTIONAL_EIDS[kind].format(match.group(1))


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


def carry_restored_states(
    last_states: dict[str, Any],
    renamed: list[tuple[str, str]],
    retarget: Any,
) -> list[str]:
    """Move restored states from old to new entity ids; return the ids moved.

    Home Assistant keys the states it restores at startup by entity_id and
    does not follow a registry rename: without this, a lock that was on, a
    cover's current mode and the shading switches would all come back at
    their defaults on the first start after the rename. *retarget(stored,
    new_id)* rebuilds one stored state under its new id.
    """
    moved: list[str] = []
    for old, new in renamed:
        if new in last_states or (stored := last_states.pop(old, None)) is None:
            continue
        last_states[new] = retarget(stored, new)
        moved.append(new)
    return moved


def resolve_helper_entity(hass: HomeAssistant, cover_entity_id: str, kind: str) -> str:
    """Return the current entity_id of a helper entity for *cover_entity_id*.

    Registry lookup by unique_id (survives renames of both the helper and the
    cover), falling back to the conventional entity_id when the entity is not
    registered yet (fresh add before platform reload).
    """
    return _lookup_helper(hass, cover_entity_id, kind) or helper_entity_id(kind, cover_entity_id)


def purge_helper_entity(hass: HomeAssistant, cover_entity_id: str, kind: str) -> None:
    """Remove a helper entity from the registry (both unique_id schemes)."""
    entity_id = _lookup_helper(hass, cover_entity_id, kind)
    if entity_id:
        er.async_get(hass).async_remove(entity_id)


def effective_behavior(behavior: str | None, stored_position: Any) -> str | None:
    """Behavior actually driving a cover in a mode, override taken into account.

    A per-cover stored position (fixed int or entity id, i.e. anything but
    None) overrides a computing behavior for that cover: the mode then acts
    as a plain position mode - auto switches stay off, lock and memory follow
    the mode's own lock flag.
    """
    if behavior is not None and stored_position is not None:
        return None
    return behavior


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
