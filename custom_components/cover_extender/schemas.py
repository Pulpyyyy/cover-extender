"""Voluptuous schemas and YAML loader for cover_extender."""
from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_FACADE,
    CONF_MODES,
    CONF_MODES_SECTION,
    CONF_ENTITY_PICTURE,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
    CONF_SHOW_ENTITIES,
    CONF_ANGLE_LEFT,
    CONF_ANGLE_RIGHT,
    CONF_EXCLUSION,
    CONF_FACADES,
    CONF_AZIMUTH,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_SOURCE): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_FACADE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AZIMUTH): vol.Coerce(float),
    }
)

_MODE_DISPLAY_SCHEMA = vol.Schema(
    {
        vol.Optional("icon",       default="mdi:help-circle"): cv.string,
        vol.Optional("color",      default="white"):           cv.string,
        vol.Optional("lock",       default=False):             cv.boolean,
        vol.Optional("auto_shade", default=False):             cv.boolean,
        vol.Optional("solar_gain", default=False):             cv.boolean,
        vol.Optional("hidden",     default=False):             cv.boolean,
    }
)

_SHADING_SCHEMA = vol.Schema(
    {
        vol.Optional("enable",           default=False): cv.boolean,
        vol.Optional("distance",         default=0.3):   vol.Coerce(float),
        vol.Optional("max_height",       default=1.5):   vol.Coerce(float),
        vol.Optional("min_height",       default=0.0):   vol.Coerce(float),
        vol.Optional("degrees",          default=90):    vol.Coerce(float),
        vol.Optional("max_elevation",    default=90):    vol.Coerce(float),
        vol.Optional("min_elevation",    default=5):     vol.Coerce(float),
        vol.Optional("minimum_position", default=10):    vol.Coerce(float),
        vol.Optional("default_position", default=100):   vol.Coerce(float),
        vol.Optional("change_threshold", default=5):     vol.Coerce(float),
        vol.Optional("time_out",         default=1):     vol.Coerce(float),
    }
)

_SOLAR_GAIN_COVER_SCHEMA = vol.Schema(
    {
        vol.Optional("enable",         default=False): cv.boolean,
        vol.Optional("position_cold",  default=0):     vol.Coerce(int),
        vol.Optional("position_solar", default=100):   vol.Coerce(int),
    }
)

_SOLAR_GAIN_GLOBAL_SCHEMA = vol.Schema(
    {
        vol.Optional("temperature_entity"):                     cv.entity_id,
        vol.Optional("temperature_threshold", default=19.0):   vol.Coerce(float),
        vol.Optional("weather_entity"):                         cv.entity_id,
        vol.Optional("good_conditions",       default=[]):      vol.All(cv.ensure_list, [cv.string]),
    }
)

_COVER_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FACADE):                       cv.string,
        vol.Optional(CONF_ENTITY_PICTURE):               cv.string,
        vol.Optional(CONF_ANGLE_LEFT,  default=85.0):   vol.Coerce(float),
        vol.Optional(CONF_ANGLE_RIGHT, default=85.0):   vol.Coerce(float),
        vol.Optional(CONF_MODES,       default={}):
            vol.Schema({cv.string: vol.Any(None, vol.Coerce(int), cv.entity_id)}),
        vol.Optional(CONF_SHADING,     default={}):     _SHADING_SCHEMA,
        vol.Optional(CONF_SOLAR_GAIN,  default={}):     _SOLAR_GAIN_COVER_SCHEMA,
        vol.Optional(CONF_EXCLUSION,   default=[]):     vol.All(cv.ensure_list, [cv.entity_id]),
    }
)


def load_covers_config(
    hass: HomeAssistant, source: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load and validate cover configuration from a YAML file.

    Returns (profiles, modes_list, facades, show_entities, solar_gain_global).
    All five dicts are empty on parse error.
    """
    if not os.path.isabs(source):
        source = hass.config.path(source)

    try:
        with open(source, encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _LOGGER.error("Cover config file not found: %s", source)
        return {}, {}, {}, {}, {}
    except yaml.YAMLError as err:
        _LOGGER.error("YAML error in %s: %s", source, err)
        return {}, {}, {}, {}, {}

    # ── Facades ───────────────────────────────────────────────────────────────
    facades: dict[str, Any] = {}
    for name, fcfg in raw.get(CONF_FACADES, {}).items():
        try:
            facades[name] = _FACADE_SCHEMA(fcfg or {})
        except vol.Invalid as err:
            _LOGGER.warning("Cover config: invalid facade '%s': %s", name, err)

    # ── Global mode display definitions ───────────────────────────────────────
    modes_list: dict[str, Any] = {}
    for mode_name, mcfg in raw.get(CONF_MODES_SECTION, {}).items():
        try:
            modes_list[mode_name] = _MODE_DISPLAY_SCHEMA(mcfg or {})
        except vol.Invalid as err:
            _LOGGER.warning("Cover config: invalid mode_display '%s': %s", mode_name, err)

    # ── Cover profiles ────────────────────────────────────────────────────────
    profiles: dict[str, Any] = {}
    for entity_id, cfg in raw.items():
        if not (isinstance(entity_id, str) and entity_id.startswith("cover.")):
            continue
        try:
            profiles[entity_id] = _COVER_PROFILE_SCHEMA(cfg or {})
        except vol.Invalid as err:
            _LOGGER.error("Cover config: invalid profile '%s': %s — skipped", entity_id, err)
            continue
        for mode_name in profiles[entity_id].get(CONF_MODES, {}):
            if mode_name not in modes_list:
                _LOGGER.warning(
                    "%s: mode '%s' not found in cover_extender_modes — lock/icon undefined",
                    entity_id, mode_name,
                )

    # ── show_entities ─────────────────────────────────────────────────────────
    raw_vas: dict = raw.get(CONF_SHOW_ENTITIES, {})
    show_entities = {
        "sun_facing": bool(raw_vas.get("sun_facing", False)),
        "auto_shade":  bool(raw_vas.get("auto_shade",  False)),
        "solar_gain":  bool(raw_vas.get("solar_gain",  False)),
    }

    # ── Solar gain global config ──────────────────────────────────────────────
    try:
        solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA(raw.get(CONF_SOLAR_GAIN, {}))
    except vol.Invalid as err:
        _LOGGER.warning("Cover config: invalid solar_gain config: %s", err)
        solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA({})

    _LOGGER.info("Loaded %d cover profiles from %s", len(profiles), source)
    return profiles, modes_list, facades, show_entities, solar_gain_global
