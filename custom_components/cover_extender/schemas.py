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
    CONF_COMMAND_INTERVAL,
    DEFAULT_COMMAND_INTERVAL,
    DEFAULT_COMMAND_INTERVAL_MS,
    SUBENTRY_TYPE_GLOBAL,
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_MODE,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_TEMPLATE,
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
        vol.Optional("behavior",   default=None):              vol.Any(None, vol.In(["auto_shade", "solar_gain"])),
        vol.Optional("hidden",     default=False):             cv.boolean,
    }
)

SHADE_DEFAULTS: dict[str, Any] = {
    "enable":           False,
    "distance":         0.4,
    "max_height":       1.8,
    "min_height":       0.0,
    "degrees":          90.0,
    "max_elevation":    90.0,
    "min_elevation":    5.0,
    "minimum_position": 15.0,
    "default_position": 100.0,
    "change_threshold": 5.0,
    "time_out":         2.0,
}

_SHADING_SCHEMA = vol.Schema(
    {
        vol.Optional("enable",           default=SHADE_DEFAULTS["enable"]):           cv.boolean,
        vol.Optional("distance",         default=SHADE_DEFAULTS["distance"]):         vol.Coerce(float),
        vol.Optional("max_height",       default=SHADE_DEFAULTS["max_height"]):       vol.Coerce(float),
        vol.Optional("min_height",       default=SHADE_DEFAULTS["min_height"]):       vol.Coerce(float),
        vol.Optional("degrees",          default=SHADE_DEFAULTS["degrees"]):          vol.Coerce(float),
        vol.Optional("max_elevation",    default=SHADE_DEFAULTS["max_elevation"]):    vol.Coerce(float),
        vol.Optional("min_elevation",    default=SHADE_DEFAULTS["min_elevation"]):    vol.Coerce(float),
        vol.Optional("minimum_position", default=SHADE_DEFAULTS["minimum_position"]): vol.Coerce(float),
        vol.Optional("default_position", default=SHADE_DEFAULTS["default_position"]): vol.Coerce(float),
        vol.Optional("change_threshold", default=SHADE_DEFAULTS["change_threshold"]): vol.Coerce(float),
        vol.Optional("time_out",         default=SHADE_DEFAULTS["time_out"]):         vol.Coerce(float),
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
        # Accept either a static float or an input_number entity id (resolved at runtime)
        vol.Optional("temperature_threshold", default=19.0):   vol.Any(vol.Coerce(float), cv.entity_id),
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
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], float]:
    """Load and validate cover configuration from a YAML file.

    Returns (profiles, modes_list, facades, show_entities, solar_gain_global, command_interval).
    All dicts are empty and command_interval defaults to DEFAULT_COMMAND_INTERVAL on parse error.
    """
    if not os.path.isabs(source):
        source = hass.config.path(source)

    try:
        with open(source, encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _LOGGER.error("Cover config file not found: %s", source)
        return {}, {}, {}, {}, {}, DEFAULT_COMMAND_INTERVAL
    except yaml.YAMLError as err:
        _LOGGER.error("YAML error in %s: %s", source, err)
        return {}, {}, {}, {}, {}, DEFAULT_COMMAND_INTERVAL

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

    # ── command_interval ──────────────────────────────────────────────────────
    try:
        command_interval = float(raw.get(CONF_COMMAND_INTERVAL, DEFAULT_COMMAND_INTERVAL))
        if command_interval < 0:
            raise ValueError("command_interval must be >= 0")
    except (ValueError, TypeError) as err:
        _LOGGER.warning("Cover config: invalid command_interval: %s — using default", err)
        command_interval = DEFAULT_COMMAND_INTERVAL

    _LOGGER.info("Loaded %d cover profiles from %s", len(profiles), source)
    return profiles, modes_list, facades, show_entities, solar_gain_global, command_interval


def build_profiles_from_subentries(
    entry: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], float]:
    """Convert UI subentries into the same 6-tuple that load_covers_config returns.

    Returns (profiles, modes_list, facades, show_entities, solar_gain_global, command_interval).
    """
    facades: dict[str, Any] = {}
    modes_list: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    show_entities: dict[str, Any] = {
        "sun_facing": False,
        "auto_shade": False,
        "solar_gain": False,
    }
    solar_gain_global: dict[str, Any] = _SOLAR_GAIN_GLOBAL_SCHEMA({})
    command_interval: float = DEFAULT_COMMAND_INTERVAL

    # ── First pass: collect cover templates ──────────────────────────────────
    templates: dict[str, dict[str, Any]] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_TEMPLATE:
            continue
        d = subentry.data
        try:
            tpl_shade = _SHADING_SCHEMA(d.get("shade") or {})
        except vol.Invalid:
            tpl_shade = _SHADING_SCHEMA({})
        try:
            tpl_sg = _SOLAR_GAIN_COVER_SCHEMA(d.get("solar_gain") or {})
        except vol.Invalid:
            tpl_sg = _SOLAR_GAIN_COVER_SCHEMA({})
        templates[d["name"]] = {
            "angle_left":  float(d.get("angle_left",  85.0)),
            "angle_right": float(d.get("angle_right", 85.0)),
            "shade":       tpl_shade,
            "solar_gain":  tpl_sg,
        }

    # ── Main pass ─────────────────────────────────────────────────────────────
    for subentry in entry.subentries.values():
        stype = subentry.subentry_type
        d = subentry.data

        if stype == SUBENTRY_TYPE_FACADE:
            facades[d["name"]] = {"azimuth": float(d.get("azimuth", 180.0))}

        elif stype == SUBENTRY_TYPE_MODE:
            name = d["name"]
            modes_list[name] = {
                "icon":     d.get("icon",     "mdi:help-circle"),
                "color":    d.get("color",    "white"),
                "lock":     bool(d.get("lock", False)),
                "behavior": d.get("behavior") or None,
                "hidden":   bool(d.get("hidden", False)),
            }

        elif stype == SUBENTRY_TYPE_COVER:
            entity_id = d["entity_id"]

            # Resolve angle / shade / solar_gain from template or cover itself
            template_name = d.get("template", "")
            if template_name:
                if template_name in templates:
                    tpl = templates[template_name]
                    angle_left  = tpl["angle_left"]
                    angle_right = tpl["angle_right"]
                    shade_cfg   = tpl["shade"]
                    sg_cfg      = tpl["solar_gain"]
                else:
                    _LOGGER.warning(
                        "Cover %s references template '%s' which does not exist — using defaults",
                        entity_id, template_name,
                    )
                    angle_left  = float(d.get("angle_left",  85.0))
                    angle_right = float(d.get("angle_right", 85.0))
                    shade_cfg   = _SHADING_SCHEMA({})
                    sg_cfg      = _SOLAR_GAIN_COVER_SCHEMA({})
            else:
                angle_left  = float(d.get("angle_left",  85.0))
                angle_right = float(d.get("angle_right", 85.0))
                try:
                    shade_cfg = _SHADING_SCHEMA(d.get("shade") or {})
                except vol.Invalid:
                    shade_cfg = _SHADING_SCHEMA({})
                try:
                    sg_cfg = _SOLAR_GAIN_COVER_SCHEMA(d.get("solar_gain") or {})
                except vol.Invalid:
                    sg_cfg = _SOLAR_GAIN_COVER_SCHEMA({})

            # Convert modes from UI format {"type": ..., "value": ...} → coordinator format
            raw_modes: dict[str, Any] = d.get("modes", {})
            modes: dict[str, Any] = {}
            for mode_name, mode_cfg in raw_modes.items():
                if isinstance(mode_cfg, dict):
                    mode_type = mode_cfg.get("type", "fixed")
                    value = mode_cfg.get("value")
                    if mode_type == "fixed":
                        try:
                            modes[mode_name] = int(value) if value is not None else None
                        except (ValueError, TypeError):
                            modes[mode_name] = None
                    elif mode_type == "entity":
                        modes[mode_name] = str(value).strip() if value else None
                    else:  # "auto"
                        modes[mode_name] = None
                else:
                    # Already in coordinator format (unlikely but safe)
                    modes[mode_name] = mode_cfg

            profiles[entity_id] = {
                CONF_FACADE:         d.get("facade") or None,
                CONF_ENTITY_PICTURE: d.get("entity_picture") or None,
                CONF_ANGLE_LEFT:     angle_left,
                CONF_ANGLE_RIGHT:    angle_right,
                CONF_MODES:          modes,
                CONF_SHADING:        shade_cfg,
                CONF_SOLAR_GAIN:     sg_cfg,
                CONF_EXCLUSION:      list(d.get("exclusion") or []),
            }

        elif stype == SUBENTRY_TYPE_GLOBAL:
            # Stored as ms (int) in UI config → convert to seconds for the coordinator
            command_interval = int(d.get("command_interval", DEFAULT_COMMAND_INTERVAL_MS)) / 1000.0
            show_entities = d.get("show_entities", show_entities)
            try:
                solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA(d.get("solar_gain") or {})
            except vol.Invalid:
                solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA({})

    _LOGGER.debug(
        "build_profiles_from_subentries: %d profiles, %d modes, %d facades, %d templates",
        len(profiles), len(modes_list), len(facades), len(templates),
    )
    return profiles, modes_list, facades, show_entities, solar_gain_global, command_interval
