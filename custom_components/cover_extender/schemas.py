"""Voluptuous schemas and options → profiles builder for cover_extender."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import (
    CONF_FACADE,
    CONF_MODES,
    CONF_ENTITY_PICTURE,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
    CONF_ANGLE_LEFT,
    CONF_ANGLE_RIGHT,
    CONF_AZIMUTH,
    CONF_TILT,
    CONF_WINDOW_KIND,
    CONF_EXCLUSION,
    CONF_INHIBITION,
    CONF_SCHEDULE,
    DEFAULT_COMMAND_INTERVAL_MS,
    OPT_CONFIG,
    SECTION_COVER,
    SECTION_FACADE,
    SECTION_GLOBAL,
    SECTION_MODE,
    SECTION_TEMPLATE,
    WALL_TILT,
)
from .schedule import KINDS as SCHEDULE_KINDS, parse_action as parse_schedule_action
from .shade import tilt_kind

_LOGGER = logging.getLogger(__name__)

SHADE_DEFAULTS: dict[str, Any] = {
    "enable":           False,
    "distance":         0.4,
    "max_height":       1.8,
    "min_height":       0.0,
    # 180 = no limit: over the zenith and down to the roof (a wall stops at 90).
    "max_elevation":    180.0,
    "min_elevation":    5.0,
    "minimum_position": 15.0,
    "default_position": 100.0,
    "change_threshold": 5.0,
    "time_out":         2.0,
    # A flat window's position while the sun touches it (see shade.py).
    "sun_position":     30.0,
}

_SHADING_SCHEMA = vol.Schema(
    {
        vol.Optional("enable",           default=SHADE_DEFAULTS["enable"]):           cv.boolean,
        vol.Optional("distance",         default=SHADE_DEFAULTS["distance"]):         vol.Coerce(float),
        vol.Optional("max_height",       default=SHADE_DEFAULTS["max_height"]):       vol.Coerce(float),
        vol.Optional("min_height",       default=SHADE_DEFAULTS["min_height"]):       vol.Coerce(float),
        vol.Optional("max_elevation",    default=SHADE_DEFAULTS["max_elevation"]):    vol.Coerce(float),
        vol.Optional("min_elevation",    default=SHADE_DEFAULTS["min_elevation"]):    vol.Coerce(float),
        vol.Optional("minimum_position", default=SHADE_DEFAULTS["minimum_position"]): vol.Coerce(float),
        vol.Optional("default_position", default=SHADE_DEFAULTS["default_position"]): vol.Coerce(float),
        vol.Optional("change_threshold", default=SHADE_DEFAULTS["change_threshold"]): vol.Coerce(float),
        vol.Optional("time_out",         default=SHADE_DEFAULTS["time_out"]):         vol.Coerce(float),
        vol.Optional("sun_position",     default=SHADE_DEFAULTS["sun_position"]):     vol.Coerce(float),
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

def lift_max_elevation(sections: dict[str, Any]) -> dict[str, Any] | None:
    """Turn every stored maximum height of 90° into 180°, "no limit".

    Heights now run past the zenith, down the far side of a roof (see
    shade.sun_height). 90° was the default, meaning no limit on a wall; on a
    roof it would now stop shading at the zenith. 180° is no limit on both,
    and on a wall the two behave alike, so nothing changes for existing
    covers. Values under 90° were chosen and stay. Returns the new sections,
    or None when there is nothing to lift.
    """
    changed = False

    def lift(value: Any) -> Any:
        nonlocal changed
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 90:
            changed = True
            return 180
        return value

    out = dict(sections)
    if SECTION_TEMPLATE in sections:
        templates = []
        for tpl in sections.get(SECTION_TEMPLATE) or []:
            tpl = dict(tpl)
            if isinstance(tpl.get("shade"), dict) and "max_elevation" in tpl["shade"]:
                tpl["shade"] = {**tpl["shade"], "max_elevation": lift(tpl["shade"]["max_elevation"])}
            templates.append(tpl)
        out[SECTION_TEMPLATE] = templates
    if SECTION_COVER in sections:
        covers = []
        for cover in sections.get(SECTION_COVER) or []:
            cover = dict(cover)
            if "shade_max_elevation" in cover:
                cover["shade_max_elevation"] = lift(cover["shade_max_elevation"])
            covers.append(cover)
        out[SECTION_COVER] = covers
    return out if changed else None


def infer_template_kinds(sections: dict[str, Any]) -> dict[str, Any] | None:
    """Give a template the kind of window all its covers have, roof or flat.

    Templates had no kind before sloped windows: they were all a wall's. One
    whose covers all sit on roof facades (or all on flat ones) becomes that
    kind, so their lengths stay read as lengths. A template shared by kinds,
    or by walls only, stays a wall's. Returns the new sections, or None when
    nothing changes.
    """
    facades = {
        f.get("name"): tilt_kind(float(f.get(CONF_TILT, WALL_TILT)))
        for f in sections.get(SECTION_FACADE) or []
    }
    kinds: dict[str, set[str]] = {}
    for cover in sections.get(SECTION_COVER) or []:
        if (name := cover.get("template")) and cover.get("facade") in facades:
            kinds.setdefault(name, set()).add(facades[cover["facade"]])
    changed = False
    templates = []
    for tpl in sections.get(SECTION_TEMPLATE) or []:
        found = kinds.get(tpl.get("name"), set())
        if CONF_WINDOW_KIND not in tpl and len(found) == 1 and (kind := next(iter(found))) != "wall":
            tpl = {**tpl, CONF_WINDOW_KIND: kind}
            changed = True
        templates.append(tpl)
    return {**sections, SECTION_TEMPLATE: templates} if changed else None


def _add_cover_profile(
    d: dict[str, Any],
    templates: dict[str, dict[str, Any]],
    profiles: dict[str, Any],
    hass: HomeAssistant | None = None,
) -> None:
    """Parse one cover item dict and append to profiles (mutates profiles in place).

    Profiles are keyed by the cover's CURRENT entity_id: when the item carries
    an entity_registry_id (v2.2+), it is resolved through the registry so a
    renamed cover keeps working. The stored entity_id remains the fallback.
    """
    entity_id = d.get("entity_id")
    if hass is not None and (rid := d.get("entity_registry_id")):
        reg = er.async_get(hass).async_get(rid)
        if reg:
            entity_id = reg.entity_id
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
        "min_elevation":    d.get("shade_min_elevation",    tpl_shade.get("min_elevation",    SHADE_DEFAULTS["min_elevation"])),
        "max_elevation":    d.get("shade_max_elevation",    tpl_shade.get("max_elevation",    SHADE_DEFAULTS["max_elevation"])),
        "minimum_position": d.get("shade_minimum_position", tpl_shade.get("minimum_position", SHADE_DEFAULTS["minimum_position"])),
        "default_position": d.get("shade_default_position", tpl_shade.get("default_position", SHADE_DEFAULTS["default_position"])),
        "change_threshold": d.get("shade_change_threshold", tpl_shade.get("change_threshold", SHADE_DEFAULTS["change_threshold"])),
        "time_out":         d.get("shade_time_out",         tpl_shade.get("time_out",         SHADE_DEFAULTS["time_out"])),
        "sun_position":     d.get("shade_sun_position",     tpl_shade.get("sun_position",     SHADE_DEFAULTS["sun_position"])),
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
        CONF_INHIBITION:     list(d.get("inhibition") or []),
        CONF_SCHEDULE:       _schedule_actions(entity_id, d.get("schedule") or {}),
    }


def _schedule_actions(entity_id: str, sched: dict[str, Any]) -> dict[str, Any]:
    """The cover's morning / evening action; one that cannot be read is dropped."""
    actions: dict[str, Any] = {}
    for kind in SCHEDULE_KINDS:
        try:
            actions[kind] = parse_schedule_action(sched.get(kind))
        except ValueError:
            _LOGGER.warning("%s: the %s schedule position cannot be read, ignored", entity_id, kind)
            actions[kind] = None
    return actions


def build_profiles_from_options(
    entry: Any,
    hass: HomeAssistant | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], float]:
    """Convert entry.options[OPT_CONFIG] into the runtime configuration 6-tuple.

    Every section has been normalised by the v1 → v2 migration, so the legacy
    subentry shapes (per-item subentries, ``{"items": [...]}`` wrappers) are
    handled there and not here — this reads plain lists and one flat dict.

    Returns (profiles, modes_list, facades, show_entities, solar_gain_global, command_interval).
    """
    facades: dict[str, Any] = {}
    modes_list: dict[str, Any] = {}
    profiles: dict[str, Any] = {}

    sections: dict[str, Any] = dict(entry.options.get(OPT_CONFIG) or {})

    # ── Global settings ───────────────────────────────────────────────────────
    # Fallback: pre-2.0 installations stored the settings as bare flat keys in
    # entry.options, before OPT_CONFIG nested them under "global".
    if sections:
        global_data: dict[str, Any] = dict(sections.get(SECTION_GLOBAL) or {})
    else:
        global_data = dict(entry.options or {})
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

    for item in sections.get(SECTION_TEMPLATE) or []:
        _add_template(item)

    # ── Main pass ─────────────────────────────────────────────────────────────
    for item in sections.get(SECTION_FACADE) or []:
        if name := item.get("name"):
            facades[name] = {
                CONF_AZIMUTH: float(item.get(CONF_AZIMUTH, 180.0)),
                CONF_TILT:    float(item.get(CONF_TILT, WALL_TILT)),
            }

    for item in sections.get(SECTION_MODE) or []:
        if name := item.get("name"):
            modes_list[name] = {
                "icon":     item.get("icon",     "mdi:help-circle"),
                "color":    item.get("color",    "#FFFFFF"),
                "lock":     bool(item.get("lock", False)),
                "behavior": item.get("behavior") or None,
                "hidden":   bool(item.get("hidden", False)),
                "priority": bool(item.get("priority", False)),
                "duration": item.get("duration") or None,
                "return_mode": item.get("return_mode") or None,
                "spares": list(item.get("spares") or []),
                "fallback": item.get("fallback") or None,
            }

    for cover_data in sections.get(SECTION_COVER) or []:
        _add_cover_profile(cover_data, templates, profiles, hass)

    _LOGGER.debug(
        "build_profiles_from_options: %d profiles, %d modes, %d facades, %d templates",
        len(profiles), len(modes_list), len(facades), len(templates),
    )
    return profiles, modes_list, facades, show_entities, solar_gain_global, command_interval
