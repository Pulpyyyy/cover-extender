"""WebSocket API for the Cover Extender admin panel.

Two commands, both admin-only:

  cover_extender/config/get
      Returns the whole configuration (facades, modes, templates, covers,
      global settings) read from entry.options[OPT_CONFIG], plus the behavior
      field table the panel builds its forms from.

  cover_extender/config/save {section, data}
      Persists ONE section back into entry.options[OPT_CONFIG].
      - section "facade" | "mode" | "template" | "cover": data is the items list
      - section "global": data is the flat settings dict

The panel never talks to the coordinator directly: persisting through
async_update_entry fires the entry's update listener, which triggers the hot
reload (_on_entry_updated). Validation stays server-side, so nothing the panel
sends can land in storage unchecked — this module is now the ONLY writer of the
configuration, the subentry wizards it grew out of having been removed from
config_flow.py once it covered all of them.

The behavior field table (defaults, bounds, units, section grouping) is SENT to
the panel rather than duplicated in JavaScript: one table, one place to change a
bound, and the forms cannot drift away from the validation that guards them.

Two structural rules are enforced here, because losing them would let the panel
corrupt what the wizards protected:
  - a facade / template / mode still referenced by a cover cannot be deleted,
  - a rename cascades to the covers referencing the old name.
Renames are detected by a set difference over names, not a same-index diff: the
panel reorders items by drag, and an index diff would read a reorder as a burst
of renames (see _rename_pair).

Templates are the one section whose stored shape differs from the edited shape:
they nest their fields under shade/solar_gain, so they are flattened on the way
out and packed on the way back in. The nesting is preserved verbatim through the
v1 → v2 options migration, so a template written back when the wizards still
existed reads back unchanged.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .helpers import resolve_helper_entity
from .schedule import DEFAULTS as SCHEDULE_DEFAULTS, KINDS as SCHEDULE_KINDS, validate_settings as validate_schedule

from .shade import tilt_kind
from .const import (
    CONF_TILT,
    CONF_WINDOW_KIND,
    WALL_TILT,
    WINDOW_KINDS,
    MODE_DURATION_MAX,
    MODE_DURATION_MIN,
    DEFAULT_COMMAND_INTERVAL_MS,
    DOMAIN,
    FALLBACK_VERSION,
    OPT_CONFIG,
    SECTION_COVER,
    SECTION_FACADE,
    SECTION_GLOBAL,
    SECTION_SCHEDULE,
    WS_SCHEDULE_PREVIEW,
    SECTION_MODE,
    SECTION_TEMPLATE,
    WEATHER_CONDITIONS,
    WS_CONFIG_GET,
    WS_CONFIG_SAVE,
)

_LOGGER = logging.getLogger(__name__)

_DATA_WS_REGISTERED = "ws_registered"

# section name used by the panel → key under entry.options[OPT_CONFIG]
_SECTIONS: dict[str, str] = {
    "facade":   SECTION_FACADE,
    "mode":     SECTION_MODE,
    "template": SECTION_TEMPLATE,
    "cover":    SECTION_COVER,
    "global":   SECTION_GLOBAL,
    "schedule": SECTION_SCHEDULE,
}

# ── Behavior fields ───────────────────────────────────────────────────────────
# The behavior fields, in the form the panel renders them from:
# name -> (default, min, max, step, unit). A unit of "" marks a boolean.
_BEHAVIOR_FIELDS: dict[str, tuple[Any, float | None, float | None, float | None, str]] = {
    # Up to 180° for a roof, which also sees the sky behind it; a wall gets
    # nothing past 90° whatever the value (see shade.faces_glass).
    "angle_left":                (85,    0, 180, 1,   "°"),
    "angle_right":               (85,    0, 180, 1,   "°"),
    "shade_distance":            (0.4,   0, 3,   0.1, "m"),
    "shade_max_height":          (1.8,   0, 3,   0.1, "m"),
    "shade_min_height":          (0.0,   0, 3,   0.1, "m"),
    # Heights read from the horizon in front, over the zenith (90°) and on a
    # roof down the other side (see shade.sun_height). 180 = no limit.
    "shade_min_elevation":       (5,     0, 180, 1,   "°"),
    "shade_max_elevation":       (180,   0, 180, 1,   "°"),
    "shade_minimum_position":    (15,    0, 100, 1,   "%"),
    "shade_default_position":    (100,   0, 100, 1,   "%"),
    "shade_change_threshold":    (5,     0, 50,  1,   "%"),
    "shade_time_out":            (2,     0, 60,  1,   "min"),
    "shade_sun_position":        (30,    0, 100, 1,   "%"),
    "solar_gain_position_solar": (100,   0, 100, 1,   "%"),
    "solar_gain_position_cold":  (0,     0, 100, 1,   "%"),
    "shade_enable":              (False, None, None, None, ""),
    "solar_gain_enable":         (False, None, None, None, ""),
}

_BEHAVIOR_FIELDS_DEFAULTS = {k: v[0] for k, v in _BEHAVIOR_FIELDS.items()}

# Display order: the grouping the panel turns into collapsible sections.
_COVER_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("geometry",   ("shade_distance", "shade_max_height", "shade_min_height",
                    "shade_sun_position")),
    ("detection",  ("angle_left", "angle_right",
                    "shade_min_elevation", "shade_max_elevation")),
    ("shading",    ("shade_enable", "shade_minimum_position", "shade_default_position",
                    "shade_change_threshold", "shade_time_out")),
    ("solar_gain", ("solar_gain_enable", "solar_gain_position_solar",
                    "solar_gain_position_cold")),
)

# Activation flags are cover-specific: a template has no counterpart for them,
# so they are never stripped as "same as the template".
_ACTIVATION_FLAGS = ("shade_enable", "solar_gain_enable")

_MODE_BEHAVIORS = (None, "auto_shade", "solar_gain")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

# entity_picture is the one free-text field that leaves this machine: it is
# copied into the cover's state attributes, so every HA frontend fetches it.
# An off-site URL would therefore beacon the installation's IP and usage rhythm
# to whoever hosts it, silently and on every dashboard load. Only host-relative
# paths are accepted — "//host/x" is protocol-relative, i.e. off-site wearing a
# relative disguise, and is rejected with everything else. An external image
# still works: drop it in www/ and point at /local/.
_PICTURE_MAX_LEN = 255

# A template is the reference the covers deviate FROM, so it has no activation
# flags of its own: those two are the only cover-specific behavior fields.
_TEMPLATE_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    (key, tuple(f for f in names if f not in _ACTIVATION_FLAGS))
    for key, names in _COVER_SECTIONS
)

# Global settings: key -> (default, kind). "entity" keys are dropped when blank
# rather than stored empty — an empty string would read as a configured entity.
_GLOBAL_BOOLS = {"show_sun_facing": True, "show_auto_shade": True, "show_solar_gain": False}
_GLOBAL_ENTITIES = ("sg_temperature_entity", "sg_temperature_threshold", "sg_weather_entity")
_DEFAULT_GOOD_CONDITIONS = ["sunny", "partlycloudy"]


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the WS commands once (idempotent across entry reloads)."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_DATA_WS_REGISTERED):
        return
    websocket_api.async_register_command(hass, ws_config_get)
    websocket_api.async_register_command(hass, ws_config_save)
    websocket_api.async_register_command(hass, ws_schedule_preview)
    domain_data[_DATA_WS_REGISTERED] = True
    _LOGGER.debug("websocket_api: commands registered")


# ── Options access ─────────────────────────────────────────────────────────────
# manifest.json declares single_config_entry, so "the" entry is the first one.

def _entry(hass: HomeAssistant) -> ConfigEntry | None:
    return next(iter(hass.config_entries.async_entries(DOMAIN)), None)


def _sections(hass: HomeAssistant) -> dict[str, Any]:
    entry = _entry(hass)
    return dict(entry.options.get(OPT_CONFIG) or {}) if entry else {}


def _items(hass: HomeAssistant, section_key: str) -> list[dict[str, Any]]:
    return [dict(it) for it in (_sections(hass).get(section_key) or [])]


def _global_data(hass: HomeAssistant) -> dict[str, Any]:
    return dict(_sections(hass).get(SECTION_GLOBAL) or {})


def _persist(hass: HomeAssistant, updates: dict[str, Any]) -> None:
    """Write one or more sections back into entry.options, in a SINGLE update.

    Takes every section at once on purpose. A rename touches two of them (the
    renamed list, and the covers that referenced the old name), and writing them
    one after the other would fire the coordinator's update listener twice for
    one user action — two full _setup_profiles, so every state subscription torn
    down and rebuilt twice.
    Worse, it would reopen a window that only stays shut by accident: the moment
    an await slips between the two writes, the listener runs with the facade
    already renamed and the covers still pointing at the old name. That name
    resolves to nothing, compute_facade_lit falls back to due south, and a
    north-facing cover gets a southern shade position — a real movement, not a
    display glitch. One write, no window, whatever the code around it does.

    async_update_entry compares the new options to the stored ones, so an
    unchanged save is a no-op and fires no reload at all.
    """
    entry = _entry(hass)
    if entry is None:
        raise vol.Invalid("cover_extender is not set up")
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, OPT_CONFIG: {**_sections(hass), **updates}},
    )


# ── Template defaults ─────────────────────────────────────────────────────────

def _defaults_from_template(tpl: dict[str, Any]) -> dict[str, Any]:
    """Behavior values a template imposes on the covers that use it."""
    shade = tpl.get("shade", {}) or {}
    sg = tpl.get("solar_gain", {}) or {}
    return {
        "angle_left":                tpl.get("angle_left",         85),
        "angle_right":               tpl.get("angle_right",        85),
        "shade_distance":            shade.get("distance",         0.4),
        "shade_max_height":          shade.get("max_height",       1.8),
        "shade_min_height":          shade.get("min_height",       0.0),
        "shade_min_elevation":       shade.get("min_elevation",    5),
        "shade_max_elevation":       shade.get("max_elevation",    180),
        "shade_minimum_position":    shade.get("minimum_position", 15),
        "shade_default_position":    shade.get("default_position", 100),
        "shade_change_threshold":    shade.get("change_threshold", 5),
        "shade_time_out":            shade.get("time_out",         2),
        "shade_sun_position":        shade.get("sun_position",     30),
        "solar_gain_position_solar": sg.get("position_solar",      100),
        "solar_gain_position_cold":  sg.get("position_cold",       0),
    }


def _flatten_template(tpl: dict[str, Any]) -> dict[str, Any]:
    """Storage shape (nested shade/solar_gain) → the flat shape the panel edits.

    The panel then renders a template with the very same behavior rows as a
    cover, and never has to know that templates nest their fields.
    """
    return {"name": tpl.get("name"), CONF_WINDOW_KIND: _template_kind(tpl),
            **_defaults_from_template(tpl)}


def _template_kind(tpl: dict[str, Any] | None) -> str:
    """The kind of window a template is for; one stored before kinds is a wall's."""
    kind = (tpl or {}).get(CONF_WINDOW_KIND)
    return kind if kind in WINDOW_KINDS else "wall"


def _facade_kind(facade: dict[str, Any] | None) -> str:
    """The kind of window a facade's slope makes."""
    try:
        return tilt_kind(float((facade or {}).get(CONF_TILT, WALL_TILT)))
    except (TypeError, ValueError):
        return "wall"


def _pack_template(flat: dict[str, Any]) -> dict[str, Any]:
    """Flat panel shape → storage shape. Inverse of _flatten_template.

    The nested layout is the coordinator's, and older backups are written in
    it too, so packing must reproduce it field for field — the panel edits a
    flat shape purely for its own convenience.
    """
    def num(key: str) -> Any:
        return flat.get(key, _BEHAVIOR_FIELDS_DEFAULTS[key])

    # A wall's template keeps the shape every template had before kinds existed.
    kind = {CONF_WINDOW_KIND: flat[CONF_WINDOW_KIND]} if flat.get(CONF_WINDOW_KIND, "wall") != "wall" else {}
    return {
        "name": flat.get("name"),
        **kind,
        "angle_left": num("angle_left"),
        "angle_right": num("angle_right"),
        "shade": {
            "distance":         num("shade_distance"),
            "max_height":       num("shade_max_height"),
            "min_height":       num("shade_min_height"),
            "min_elevation":    num("shade_min_elevation"),
            "max_elevation":    num("shade_max_elevation"),
            "minimum_position": num("shade_minimum_position"),
            "default_position": num("shade_default_position"),
            "change_threshold": num("shade_change_threshold"),
            "time_out":         num("shade_time_out"),
            "sun_position":     num("shade_sun_position"),
        },
        "solar_gain": {
            "position_solar": num("solar_gain_position_solar"),
            "position_cold":  num("solar_gain_position_cold"),
        },
    }


def _strip_template_defaults(
    item: dict[str, Any], tpl: dict[str, Any] | None
) -> dict[str, Any]:
    """Drop behavior values equal to the template's — keep only true overrides.

    Without a template the values are the cover's own and all are kept.
    Activation flags always survive: they have no template counterpart.
    """
    if not tpl:
        return item
    tpl_vals = _defaults_from_template(tpl)
    out = dict(item)
    for key in _BEHAVIOR_FIELDS:
        if key in _ACTIVATION_FLAGS or key not in out:
            continue
        if key in tpl_vals and out[key] == tpl_vals[key]:
            del out[key]
    return out


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_named_items(items: list[dict[str, Any]]) -> str | None:
    """Facades / modes / templates: non-empty unique names."""
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            return "name_required"
        if name in seen:
            return f"name_exists:{name}"
        seen.add(name)
        item["name"] = name
    return None


def _validate_modes(items: list[dict[str, Any]]) -> str | None:
    """Mode-specific shape: behavior, colour, and the boolean flags."""
    for item in items:
        behavior = item.get("behavior") or None
        if behavior not in _MODE_BEHAVIORS:
            return f"behavior_invalid:{item.get('name')}"
        item["behavior"] = behavior
        colour = str(item.get("color") or "#FFFFFF")
        if not _HEX_COLOR.match(colour):
            return f"color_invalid:{item.get('name')}"
        item["color"] = colour.upper()
        item["icon"] = str(item.get("icon") or "mdi:help-circle")
        item["lock"] = bool(item.get("lock", False))
        item["hidden"] = bool(item.get("hidden", False))
        item["priority"] = bool(item.get("priority", False))
        duration = item.get("duration")
        if duration in (None, "", 0, False):
            item["duration"] = None
        elif (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or not MODE_DURATION_MIN <= duration <= MODE_DURATION_MAX
        ):
            return f"duration_invalid:{item.get('name')}"
    # A timed mode ends on its fixed return mode, or on the cover's base mode
    # when it has none. The fixed one must be an existing NON-timed mode: that
    # is what guarantees every countdown ends on a mode that starts no other.
    names = {it.get("name") for it in items}
    timed = {it.get("name") for it in items if it.get("duration")}
    for item in items:
        # The modes this one does not replace in a grouped request, and the
        # one it falls back to on covers it is not linked to.
        own = item.get("name")
        item["spares"] = list(dict.fromkeys(
            m for m in (item.get("spares") or []) if m in names and m != own
        ))
        fallback = item.get("fallback") or None
        if fallback is not None and (fallback not in names or fallback == own):
            return f"fallback_invalid:{own}"
        item["fallback"] = fallback
    for item in items:
        target = item.get("return_mode") or None
        if not item.get("duration"):
            item["return_mode"] = None
        elif target is not None and target not in names:
            return f"return_mode_invalid:{item.get('name')}"
        elif target is not None and target in timed:
            # Usually not a bad choice here but a later edit there: the target
            # was given a duration after being picked as a return mode.
            return f"return_mode_timed:{target}:{item.get('name')}"
        else:
            item["return_mode"] = target
    return None


def _behavior_errors(label: Any, effective: dict[str, Any]) -> str | None:
    """Cross-field checks, on the EFFECTIVE values (template + overrides).

    Checking the stored item alone would miss a cover that overrides only
    ``shade_min_height``, above a max height it inherits and never restates.
    *label* names the offender in the message (a cover's entity_id, a template's
    name) — the same check serves both.
    """
    if effective.get("shade_min_height", 0) > effective.get("shade_max_height", 3):
        return f"min_height_above_max:{label}"
    if effective.get("shade_min_elevation", 0) > effective.get("shade_max_elevation", 180):
        return f"min_elevation_above_max:{label}"
    return None


def _coerce_behavior_number(name: str, raw: Any) -> Any | None:
    """A behavior value clamped to its declared bounds, or None if not a number.

    Ints stay ints: a step of 1 written back as 15.0 would churn the stored data
    on every save and make the "same as the template" comparison miss.
    """
    default, lo, hi, step, _unit = _BEHAVIOR_FIELDS[name]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if lo is not None:
        value = max(float(lo), min(float(hi), value))
    return int(round(value)) if isinstance(default, int) and not isinstance(default, bool) \
        else round(value, 3)


def _validate_facades(items: list[dict[str, Any]]) -> str | None:
    """Facades: an azimuth in degrees, clamped to a compass, and a slope.

    The slope is stored only off the vertical: a wall keeps the shape every
    facade had before slopes existed, so saving one changes nothing.
    """
    for item in items:
        try:
            azimuth = float(item.get("azimuth", 180))
            tilt = float(item.get(CONF_TILT, WALL_TILT))
        except (TypeError, ValueError):
            return f"azimuth_invalid:{item.get('name')}"
        if not 0 <= azimuth <= 360:
            return f"azimuth_invalid:{item.get('name')}"
        if not 0 <= tilt <= WALL_TILT:
            return f"tilt_invalid:{item.get('name')}"
        item["azimuth"] = int(round(azimuth))
        if int(round(tilt)) == WALL_TILT:
            item.pop(CONF_TILT, None)
        else:
            item[CONF_TILT] = int(round(tilt))
        # Nothing else belongs in a facade; drop whatever the panel echoed back.
        for key in list(item):
            if key not in ("name", "azimuth", CONF_TILT):
                del item[key]
    return None


def _validate_templates(items: list[dict[str, Any]]) -> str | None:
    """Templates: every behavior field present and sane, then packed for storage.

    The panel sends the flat shape; what lands in the options is the nested one
    the config flow and the coordinator already read.
    """
    for idx, item in enumerate(items):
        kind = item.get(CONF_WINDOW_KIND) or "wall"
        if kind not in WINDOW_KINDS:
            return f"window_kind_invalid:{item['name']}"
        flat: dict[str, Any] = {"name": item["name"], CONF_WINDOW_KIND: kind}
        for name in _BEHAVIOR_FIELDS:
            if name in _ACTIVATION_FLAGS:
                continue
            value = _coerce_behavior_number(name, item.get(name, _BEHAVIOR_FIELDS_DEFAULTS[name]))
            if value is None:
                return f"field_invalid:{name}"
            flat[name] = value
        if error := _behavior_errors(item["name"], flat):
            return error
        items[idx] = _pack_template(flat)
    return None


def _validate_global(data: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Global settings: the cleaned dict, or an error code.

    Returns a rebuilt dict rather than editing in place — anything the panel
    invented that is not a known setting is dropped instead of persisted.
    """
    out: dict[str, Any] = {}

    try:
        interval = int(float(data.get("command_interval", DEFAULT_COMMAND_INTERVAL_MS)))
    except (TypeError, ValueError):
        return {}, "interval_invalid"
    if not 0 <= interval <= 5000:
        return {}, "interval_invalid"
    out["command_interval"] = interval

    for key, default in _GLOBAL_BOOLS.items():
        out[key] = bool(data.get(key, default))

    for key in _GLOBAL_ENTITIES:
        raw = data.get(key)
        if isinstance(raw, str):
            if value := raw.strip():
                out[key] = value
        elif raw is not None:
            # schemas.py accepts a bare number for the threshold (legacy config).
            # Stringifying it here would silently rewrite a working setting.
            out[key] = raw

    conditions = data.get("sg_good_conditions", _DEFAULT_GOOD_CONDITIONS)
    if not isinstance(conditions, list):
        return {}, "conditions_invalid"
    for condition in conditions:
        if condition not in WEATHER_CONDITIONS:
            return {}, f"condition_unknown:{condition}"
    out["sg_good_conditions"] = list(conditions)

    return out, None


def _validate_mode_cfgs(item: dict[str, Any], mode_names: set[str]) -> str | None:
    """Per-cover mode positions: known mode, known shape, position in range."""
    modes = item.get("modes") or {}
    if not isinstance(modes, dict):
        return f"modes_invalid:{item.get('entity_id')}"
    for name, cfg in modes.items():
        if name not in mode_names:
            return f"mode_unknown:{name}"
        if not isinstance(cfg, dict):
            return f"mode_cfg_invalid:{name}"
        kind = cfg.get("type")
        if kind == "fixed":
            value = cfg.get("value")
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                return f"position_out_of_range:{name}"
        elif kind == "entity":
            if not str(cfg.get("value") or "").strip():
                return f"mode_entity_required:{name}"
        elif kind != "auto":
            return f"mode_cfg_invalid:{name}"
    return None


def _validate_covers(hass: HomeAssistant, items: list[dict[str, Any]]) -> str | None:
    """Covers: unique entity_id, known facade/template, sane behavior and modes.

    Also strips the values a cover shares with its template, so the stored item
    keeps only genuine overrides — exactly what the config flow persists.
    """
    facades = {it.get("name") for it in _items(hass, SECTION_FACADE)}
    templates = {it.get("name"): it for it in _items(hass, SECTION_TEMPLATE)}
    mode_names = {it.get("name") for it in _items(hass, SECTION_MODE)}
    registry = er.async_get(hass)
    seen: set[str] = set()

    for idx, item in enumerate(items):
        entity_id = str(item.get("entity_id") or "").strip()
        if not entity_id:
            return "entity_required"
        # The domain matters beyond tidiness: a profile makes the coordinator
        # write attributes onto the entity with hass.states.async_set and mint
        # helper entities for it. Both are wrong on anything but a cover.
        if not entity_id.startswith("cover."):
            return f"cover_domain:{entity_id}"
        if entity_id in seen:
            return f"cover_exists:{entity_id}"
        seen.add(entity_id)

        picture = str(item.get("entity_picture") or "").strip()
        if picture:
            if (
                len(picture) > _PICTURE_MAX_LEN
                or not picture.startswith("/")
                or picture.startswith("//")
            ):
                return f"picture_invalid:{entity_id}"
            item["entity_picture"] = picture
        else:
            item.pop("entity_picture", None)

        facade = item.get("facade")
        if not facade or facade not in facades:
            return f"facade_required:{entity_id}"

        template_name = item.get("template") or None
        if template_name and template_name not in templates:
            return f"template_unknown:{template_name}"

        if error := _validate_mode_cfgs(item, mode_names):
            return error
        if error := _validate_cover_schedule(hass, item, entity_id):
            return error

        tpl = templates.get(template_name) if template_name else None
        effective = {**_BEHAVIOR_FIELDS_DEFAULTS, **(_defaults_from_template(tpl) if tpl else {}),
                     **{k: v for k, v in item.items() if k in _BEHAVIOR_FIELDS}}
        if error := _behavior_errors(entity_id, effective):
            return error

        # Retired in 4.0: shading follows the left / right angles. A value left
        # over from an older version goes with the next save.
        item.pop("shade_degrees", None)
        items[idx] = item = _strip_template_defaults(item, tpl)

        # Immutable link to the entity, so it survives an entity_id rename.
        reg = registry.async_get(entity_id)
        if reg:
            item["entity_registry_id"] = reg.id
        else:
            item.pop("entity_registry_id", None)
    return None



def _kind_mismatch(
    hass: HomeAssistant, updates: dict[str, Any]
) -> str | None:
    """A cover whose template is for another kind of window than its facade.

    A template's heights are a wall's and its lengths a roof's: on a facade of
    another kind they would be read wrong. Checked on whatever the save leaves
    behind, the updated sections and the stored others.
    """
    def section(key: str) -> list[dict[str, Any]]:
        return updates[key] if key in updates else _items(hass, key)

    facades = {f.get("name"): f for f in section(SECTION_FACADE)}
    templates = {t.get("name"): t for t in section(SECTION_TEMPLATE)}
    for cover in section(SECTION_COVER):
        tpl = templates.get(cover.get("template") or None)
        facade = facades.get(cover.get("facade"))
        if tpl is None or facade is None:
            continue
        if _template_kind(tpl) != _facade_kind(facade):
            return f"window_kind_mismatch:{cover.get('entity_id')}:{tpl.get('name')}:{facade.get('name')}"
    return None


def _referencing_covers(
    hass: HomeAssistant, section: str, name: str
) -> list[str]:
    """entity_ids of the covers referencing facade / template / mode *name*."""
    out: list[str] = []
    for item in _items(hass, SECTION_COVER):
        if section == "facade":
            referenced = item.get("facade") == name
        elif section == "template":
            referenced = item.get("template") == name
        else:
            referenced = name in (item.get("modes") or {})
        if referenced:
            out.append(str(item.get("entity_id", "")))
    return out


def _name_diff(
    old_items: list[dict[str, Any]], new_items: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Names that vanished and names that appeared, ignoring order."""
    old = [str(it.get("name")) for it in old_items if it.get("name")]
    new = [str(it.get("name")) for it in new_items if it.get("name")]
    return [n for n in old if n not in set(new)], [n for n in new if n not in set(old)]


def _rename_pair(
    old_items: list[dict[str, Any]], new_items: list[dict[str, Any]]
) -> tuple[str, str] | None:
    """The (old, new) name of a rename, or None.

    Set difference, NOT a same-index diff: the panel can reorder items by drag,
    and an index diff reads a reorder as a burst of renames — which would then
    cascade into every cover's mode map and scramble it. A rename is exactly one
    name gone and one name appeared, at unchanged list length.
    """
    removed, added = _name_diff(old_items, new_items)
    if len(old_items) == len(new_items) and len(removed) == 1 and len(added) == 1:
        return removed[0], added[0]
    return None


def _deletion_blocked(
    hass: HomeAssistant, section: str, old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> str | None:
    """Refuse to drop a facade / template / mode a cover still points at.

    A name that disappeared as half of a rename is not a deletion —
    _rename_pair cascades that instead.
    """
    if section not in ("facade", "template", "mode"):
        return None
    if _rename_pair(old_items, new_items) is not None:
        return None
    removed, _ = _name_diff(old_items, new_items)
    for name in removed:
        if users := _referencing_covers(hass, section, name):
            return f"in_use:{name}:{len(users)}:{', '.join(users)}"
    return None


def _renamed_covers(
    hass: HomeAssistant, section: str, old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Covers rewritten for a facade / template / mode rename, else None.

    Returns the new list instead of writing it: the caller folds it into the
    same async_update_entry as the renamed section, so the two never land
    separately (see _persist).
    """
    if section not in ("facade", "template", "mode"):
        return None
    pair = _rename_pair(old_items, new_items)
    if pair is None:
        return None
    old, new = pair
    covers = _items(hass, SECTION_COVER)
    changed = False
    for it in covers:
        if section == "facade" and it.get("facade") == old:
            it["facade"] = new
            changed = True
        elif section == "template" and it.get("template") == old:
            it["template"] = new
            changed = True
        elif section == "mode" and old in (it.get("modes") or {}):
            it["modes"] = {(new if k == old else k): v for k, v in it["modes"].items()}
            sched = dict(it.get("schedule") or {})
            it["schedule"] = {k: (new if v == old else v) for k, v in sched.items()}
            changed = True
    if not changed:
        return None
    _LOGGER.debug("websocket_api: cascading rename %r -> %r to covers", old, new)
    return covers


def _behavior_schema() -> dict[str, Any]:
    """The field table the panel renders its behavior forms from.

    Two section lists, one field table: a cover and a template are edited with
    the same rows, the template's list simply omits the activation flags.
    """
    return {
        "sections": [{"key": key, "fields": list(names)} for key, names in _COVER_SECTIONS],
        "template_sections": [
            {"key": key, "fields": list(names)} for key, names in _TEMPLATE_SECTIONS
        ],
        "fields": {
            name: {
                "default": default,
                "min": lo,
                "max": hi,
                "step": step,
                "unit": unit,
                "type": "boolean" if unit == "" else "number",
            }
            for name, (default, lo, hi, step, unit) in _BEHAVIOR_FIELDS.items()
        },
    }


# ── Commands ──────────────────────────────────────────────────────────────────

@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): WS_CONFIG_GET})
@websocket_api.async_response
async def ws_config_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the full configuration for the admin panel."""
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version or FALLBACK_VERSION)
    except Exception:  # noqa: BLE001
        version = FALLBACK_VERSION
    connection.send_result(msg["id"], {
        "version":   version,
        "facades":   _items(hass, SECTION_FACADE),
        "modes":     _items(hass, SECTION_MODE),
        # Flattened on the way out, packed again on save: the panel edits one
        # shape for covers and templates alike.
        "templates": [_flatten_template(t) for t in _items(hass, SECTION_TEMPLATE)],
        "covers":    _items(hass, SECTION_COVER),
        # The live entity ids of each cover's mode selector and lock (they may
        # have been renamed), so the panel can read their state from hass.
        "helpers":   {
            c["entity_id"]: {
                "select": resolve_helper_entity(hass, c["entity_id"], "select_mode"),
                "lock":   resolve_helper_entity(hass, c["entity_id"], "lock"),
            }
            for c in _items(hass, SECTION_COVER) if c.get("entity_id")
        },
        "global":    _global_data(hass),
        "schedule":  dict(_sections(hass).get(SECTION_SCHEDULE) or {}),
        "schedule_defaults": SCHEDULE_DEFAULTS,
        "behavior":  _behavior_schema(),
        "weather_conditions": list(WEATHER_CONDITIONS),
        "defaults":  {"command_interval": DEFAULT_COMMAND_INTERVAL_MS},
    })


# ── Schedules ─────────────────────────────────────────────────────────────────

def _timed_mode_names(hass: HomeAssistant, items: list[dict[str, Any]] | None = None) -> set[str]:
    modes = items if items is not None else _items(hass, SECTION_MODE)
    return {it.get("name") for it in modes if it.get("duration")}


def _validate_cover_schedule(hass: HomeAssistant, item: dict[str, Any], entity_id: str) -> str | None:
    """A cover's morning / evening mode: linked to it, and without a duration.

    A mode unlinked from the cover in the matrix is dropped from its schedule
    rather than refused: the unlink is what the user asked for, and a schedule
    cannot apply a mode the cover does not have.
    """
    sched = item.get("schedule") or {}
    linked = item.get("modes") or {}
    timed = _timed_mode_names(hass)
    clean: dict[str, str | None] = {}
    for kind in SCHEDULE_KINDS:
        mode = sched.get(kind) or None
        if mode is not None and mode not in linked:
            mode = None
        if mode is not None and mode in timed:
            return f"schedule_mode_timed:{mode}"
        clean[kind] = mode
    if any(clean.values()):
        item["schedule"] = clean
    else:
        item.pop("schedule", None)
    return None


def _scheduled_mode_timed(
    hass: HomeAssistant, items: list[dict[str, Any]], old_items: list[dict[str, Any]]
) -> str | None:
    """Refuse giving a duration to a mode a cover's schedule applies."""
    pair = _rename_pair(old_items, items)
    for mode in _timed_mode_names(hass, items):
        old_name = pair[0] if pair and pair[1] == mode else mode
        users = [
            c.get("entity_id") for c in _items(hass, SECTION_COVER)
            if old_name in (c.get("schedule") or {}).values()
        ]
        if users:
            return f"schedule_mode_timed:{mode}"
    return None


def _save_schedule(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The house's schedules and each cover's morning / evening mode, saved in
    ONE write (see _persist): one reload, never half of it applied.

    data: {"house": {"morning": {...}, "evening": {...}},
           "covers": {cover_entity_id: {"morning": mode|None, "evening": mode|None}}}
    """
    data = msg["data"]
    if not isinstance(data, dict):
        connection.send_error(msg["id"], "invalid_format", "schedule expects a dict")
        return
    house = {k: v for k, v in (data.get("house") or {}).items() if k in SCHEDULE_KINDS}
    for kind, cfg in house.items():
        if error := validate_schedule(cfg):
            connection.send_error(msg["id"], "invalid_config", f"{error}:{kind}")
            return
    covers = _items(hass, SECTION_COVER)
    wanted = data.get("covers") or {}
    for item in covers:
        if item.get("entity_id") in wanted:
            item["schedule"] = dict(wanted[item["entity_id"]] or {})
        if error := _validate_cover_schedule(hass, item, item.get("entity_id")):
            connection.send_error(msg["id"], "invalid_config", error)
            return
    _persist(hass, {SECTION_SCHEDULE: house, SECTION_COVER: covers})
    _LOGGER.debug("websocket_api: saved schedules (%s)", ", ".join(house) or "none")
    connection.send_result(msg["id"], {"saved": True})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): WS_SCHEDULE_PREVIEW,
    vol.Required("kind"): vol.In(SCHEDULE_KINDS),
    vol.Required("settings"): dict,
})
@websocket_api.async_response
async def ws_schedule_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """The curve the panel draws while the user drags its handles."""
    entry = _entry(hass)
    coordinator = getattr(entry, "runtime_data", None) if entry else None
    if coordinator is None:
        connection.send_error(msg["id"], "not_ready", "cover_extender is not set up")
        return
    if error := validate_schedule(msg["settings"]):
        connection.send_result(msg["id"], {"error": error})
        return
    connection.send_result(msg["id"], coordinator.schedule_preview(msg["kind"], msg["settings"]))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): WS_CONFIG_SAVE,
    vol.Required("section"): vol.In(_SECTIONS),
    vol.Required("data"): vol.Any(list, dict),
})
@websocket_api.async_response
async def ws_config_save(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist one section of the configuration."""
    section: str = msg["section"]
    section_key = _SECTIONS[section]

    if section == "schedule":
        _save_schedule(hass, connection, msg)
        return

    if section == "global":
        if not isinstance(msg["data"], dict):
            connection.send_error(msg["id"], "invalid_format", "global expects a dict")
            return
        data, error = _validate_global(dict(msg["data"]))
        if error:
            connection.send_error(msg["id"], "invalid_config", error)
            return
        _persist(hass, {section_key: data})
        _LOGGER.debug("websocket_api: saved global settings")
        connection.send_result(msg["id"], {"saved": True})
        return

    if not isinstance(msg["data"], list):
        connection.send_error(msg["id"], "invalid_format", f"{section} expects a list")
        return
    items = [dict(it) for it in msg["data"]]
    old_items = _items(hass, section_key)

    # A renamed mode is renamed in the other modes' return mode too, before
    # validation would refuse them for pointing at a name that is gone.
    if section == "mode" and (pair := _rename_pair(old_items, items)) is not None:
        for it in items:
            if it.get("return_mode") == pair[0]:
                it["return_mode"] = pair[1]
            if it.get("fallback") == pair[0]:
                it["fallback"] = pair[1]
            it["spares"] = [pair[1] if m == pair[0] else m for m in (it.get("spares") or [])]
    elif section == "mode":
        # A deleted mode simply leaves the others' spared lists.
        gone = set(_name_diff(old_items, items)[0])
        for it in items:
            it["spares"] = [m for m in (it.get("spares") or []) if m not in gone]

    if section == "cover":
        error = _validate_covers(hass, items)
    else:
        error = _validate_named_items(items)
        if not error and section == "mode":
            error = _validate_modes(items)
        elif not error and section == "facade":
            error = _validate_facades(items)
        elif not error and section == "template":
            error = _validate_templates(items)
    if error:
        connection.send_error(msg["id"], "invalid_config", error)
        return

    if error := _deletion_blocked(hass, section, old_items, items):
        connection.send_error(msg["id"], "in_use", error)
        return
    if section == "mode" and (error := _scheduled_mode_timed(hass, items, old_items)):
        connection.send_error(msg["id"], "invalid_config", error)
        return

    updates: dict[str, Any] = {section_key: items}
    if (covers := _renamed_covers(hass, section, old_items, items)) is not None:
        updates[SECTION_COVER] = covers
    if section in ("facade", "template", "cover") and (error := _kind_mismatch(hass, updates)):
        connection.send_error(msg["id"], "invalid_config", error)
        return
    _persist(hass, updates)
    _LOGGER.debug("websocket_api: saved %s (%d item(s))", section, len(items))
    connection.send_result(msg["id"], {"saved": True, "count": len(items)})
