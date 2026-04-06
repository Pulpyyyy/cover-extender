"""Shared stateless helpers for cover_extender."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENTITY_PICTURE,
    CONF_FACADE,
    CONF_MODES,
    CONF_SHADING,
    ATTR_FACADE,
    ATTR_MODES,
    ATTR_ENABLE_AUTO_SHADE,
)

_LOGGER = logging.getLogger(__name__)


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
