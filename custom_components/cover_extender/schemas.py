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
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_GLOBAL,
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
        vol.Optional("color",      default="#FFFFFF"):          cv.string,
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
        vol.Optional("good_conditions",       default=["sunny", "partlycloudy"]): vol.All(cv.ensure_list, [cv.string]),
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


def _add_cover_profile(
    d: dict[str, Any],
    templates: dict[str, dict[str, Any]],
    profiles: dict[str, Any],
) -> None:
    """Parse one cover item dict and append to profiles (mutates profiles in place)."""
    entity_id = d.get("entity_id")
    if not entity_id:
        return

    # Resolve template data for fallback values
    template_name = d.get("template", "")
    tpl: dict[str, Any] = {}
    if template_name:
        if template_name in templates:
            tpl = templates[template_name]
        else:
            _LOGGER.warning(
                "Cover %s references template '%s' which does not exist — using defaults",
                entity_id, template_name,
            )
    tpl_shade: dict[str, Any] = tpl.get("shade", {})
    tpl_sg:    dict[str, Any] = tpl.get("solar_gain", {})

    # Enable flags: from cover data (new format), or template (backward compat)
    shade_enable = d.get("shade_enable", tpl_shade.get("enable", SHADE_DEFAULTS["enable"]))
    sg_enable    = d.get("solar_gain_enable", tpl_sg.get("enable", False))

    # Angles: cover overrides template overrides default
    angle_left  = float(d.get("angle_left",  tpl.get("angle_left",  85.0)))
    angle_right = float(d.get("angle_right", tpl.get("angle_right", 85.0)))

    # Shade config: cover overrides template overrides SHADE_DEFAULTS
    shade_raw: dict[str, Any] = {
        "enable":           shade_enable,
        "distance":         d.get("shade_distance",         tpl_shade.get("distance",         SHADE_DEFAULTS["distance"])),
        "max_height":       d.get("shade_max_height",       tpl_shade.get("max_height",       SHADE_DEFAULTS["max_height"])),
        "min_height":       d.get("shade_min_height",       tpl_shade.get("min_height",       SHADE_DEFAULTS["min_height"])),
        "degrees":          d.get("shade_degrees",          tpl_shade.get("degrees",          SHADE_DEFAULTS["degrees"])),
        "min_elevation":    d.get("shade_min_elevation",    tpl_shade.get("min_elevation",    SHADE_DEFAULTS["min_elevation"])),
        "max_elevation":    d.get("shade_max_elevation",    tpl_shade.get("max_elevation",    SHADE_DEFAULTS["max_elevation"])),
        "minimum_position": d.get("shade_minimum_position", tpl_shade.get("minimum_position", SHADE_DEFAULTS["minimum_position"])),
        "default_position": d.get("shade_default_position", tpl_shade.get("default_position", SHADE_DEFAULTS["default_position"])),
        "change_threshold": d.get("shade_change_threshold", tpl_shade.get("change_threshold", SHADE_DEFAULTS["change_threshold"])),
        "time_out":         d.get("shade_time_out",         tpl_shade.get("time_out",         SHADE_DEFAULTS["time_out"])),
    }
    try:
        shade_cfg = _SHADING_SCHEMA(shade_raw)
    except vol.Invalid:
        shade_cfg = _SHADING_SCHEMA({"enable": shade_enable})

    # Solar-gain config: cover overrides template overrides defaults
    sg_raw: dict[str, Any] = {
        "enable":         sg_enable,
        "position_solar": d.get("solar_gain_position_solar", tpl_sg.get("position_solar", 100)),
        "position_cold":  d.get("solar_gain_position_cold",  tpl_sg.get("position_cold",  0)),
    }
    try:
        sg_cfg = _SOLAR_GAIN_COVER_SCHEMA(sg_raw)
    except vol.Invalid:
        sg_cfg = _SOLAR_GAIN_COVER_SCHEMA({"enable": sg_enable})

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


def build_profiles_from_subentries(
    entry: Any,
    hass: HomeAssistant | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], float]:
    """Convert UI subentries into the same 6-tuple that load_covers_config returns.

    When *hass* is provided every config entry for the domain is scanned so
    that subentries created under a different entry (e.g. after a YAML→UI
    migration that left behind a stale entry) are also picked up.

    Returns (profiles, modes_list, facades, show_entities, solar_gain_global, command_interval).
    """
    facades: dict[str, Any] = {}
    modes_list: dict[str, Any] = {}
    profiles: dict[str, Any] = {}

    # Determine the full set of entries to scan for subentries
    if hass is not None:
        all_entries: list[Any] = hass.config_entries.async_entries(DOMAIN)
    else:
        all_entries = [entry]

    # ── Global settings live in the "global" singleton subentry ─────────────────
    global_data: dict[str, Any] = {}
    for _e in all_entries:
        for _sub in _e.subentries.values():
            if _sub.subentry_type == SUBENTRY_TYPE_GLOBAL:
                global_data = dict(_sub.data)
                break
        if global_data:
            break
    # Fallback: support legacy installations that stored global settings in options
    if not global_data:
        global_data = entry.options or {}
    command_interval: float = int(global_data.get("command_interval", DEFAULT_COMMAND_INTERVAL_MS)) / 1000.0

    # UI stores individual flat keys (show_sun_facing, show_auto_shade, show_solar_gain)
    show_entities: dict[str, Any] = {
        "sun_facing": bool(global_data.get("show_sun_facing", False)),
        "auto_shade":  bool(global_data.get("show_auto_shade", False)),
        "solar_gain":  bool(global_data.get("show_solar_gain", False)),
    }

    # UI stores solar-gain config as flat sg_* keys
    _sg_raw: dict[str, Any] = {}
    if entity := global_data.get("sg_temperature_entity"):
        _sg_raw["temperature_entity"] = entity
    if (threshold := global_data.get("sg_temperature_threshold")) is not None:
        try:
            _sg_raw["temperature_threshold"] = float(threshold)
        except (ValueError, TypeError):
            _sg_raw["temperature_threshold"] = str(threshold)
    if entity := global_data.get("sg_weather_entity"):
        _sg_raw["weather_entity"] = entity
    if conditions := global_data.get("sg_good_conditions"):
        _sg_raw["good_conditions"] = conditions
    try:
        solar_gain_global: dict[str, Any] = _SOLAR_GAIN_GLOBAL_SCHEMA(_sg_raw)
    except vol.Invalid:
        solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA({})

    # ── First pass: collect cover templates ──────────────────────────────────
    templates: dict[str, dict[str, Any]] = {}

    def _add_template(item: dict[str, Any]) -> None:
        name = item.get("name")
        if not name:
            return
        try:
            tpl_shade = _SHADING_SCHEMA(item.get("shade") or {})
        except vol.Invalid:
            tpl_shade = _SHADING_SCHEMA({})
        try:
            tpl_sg = _SOLAR_GAIN_COVER_SCHEMA(item.get("solar_gain") or {})
        except vol.Invalid:
            tpl_sg = _SOLAR_GAIN_COVER_SCHEMA({})
        templates[name] = {
            "angle_left":  float(item.get("angle_left",  85.0)),
            "angle_right": float(item.get("angle_right", 85.0)),
            "shade":       tpl_shade,
            "solar_gain":  tpl_sg,
        }

    for _entry in all_entries:
        for subentry in _entry.subentries.values():
            if subentry.subentry_type != SUBENTRY_TYPE_TEMPLATE:
                continue
            d = subentry.data
            if "items" in d:
                # Singleton format: {"items": [{name, angle_left, ...}, ...]}
                for item in d["items"]:
                    _add_template(item)
            else:
                # Legacy individual format: {name, angle_left, ...}
                _add_template(d)

    # ── Main pass ─────────────────────────────────────────────────────────────
    for _entry in all_entries:
        for subentry in _entry.subentries.values():
            stype = subentry.subentry_type
            d = subentry.data

            if stype == SUBENTRY_TYPE_FACADE:
                if "items" in d:
                    # Current singleton format: {"items": [{"name": ..., "azimuth": ...}, ...]}
                    for item in d["items"]:
                        if name := item.get("name"):
                            facades[name] = {"azimuth": float(item.get("azimuth", 180.0))}
                elif name := d.get("name"):
                    # Legacy individual format: {"name": ..., "azimuth": ...}
                    facades[name] = {"azimuth": float(d.get("azimuth", 180.0))}

            elif stype == SUBENTRY_TYPE_MODE:
                if "items" in d:
                    # Current singleton format: {"items": [...]}
                    for item in d["items"]:
                        if name := item.get("name"):
                            modes_list[name] = {
                                "icon":     item.get("icon",     "mdi:help-circle"),
                                "color":    item.get("color",    "#FFFFFF"),
                                "lock":     bool(item.get("lock", False)),
                                "behavior": item.get("behavior") or None,
                                "hidden":   bool(item.get("hidden", False)),
                            }
                elif name := d.get("name"):
                    # Legacy individual format
                    modes_list[name] = {
                        "icon":     d.get("icon",     "mdi:help-circle"),
                        "color":    d.get("color",    "#FFFFFF"),
                        "lock":     bool(d.get("lock", False)),
                        "behavior": d.get("behavior") or None,
                        "hidden":   bool(d.get("hidden", False)),
                    }

            elif stype == SUBENTRY_TYPE_COVER:
                # Support both new singleton format {"items": [...]} and legacy individual format
                cover_items: list[dict[str, Any]] = d.get("items") if "items" in d else [d]
                for cover_data in cover_items:
                    _add_cover_profile(cover_data, templates, profiles)



    _LOGGER.debug(
        "build_profiles_from_subentries: %d profiles, %d modes, %d facades, %d templates",
        len(profiles), len(modes_list), len(facades), len(templates),
    )
    return profiles, modes_list, facades, show_entities, solar_gain_global, command_interval
