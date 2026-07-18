"""Config flow for Cover Extender.

UI mode: configuration via subentries.
  - Facades, modes, templates → singleton subentries (one subentry holds all items)
  - Covers                    → individual subentries (one subentry per entity)
"""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryFlow, ConfigEntry
from homeassistant.data_entry_flow import section
from homeassistant.helpers import (
    entity_registry as er,
    selector,
    translation as ha_translation,
)
from homeassistant.core import HomeAssistant, callback

from .const import (
    DEFAULT_COMMAND_INTERVAL_MS,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_GLOBAL,
    SUBENTRY_TYPE_MODE,
    SUBENTRY_TYPE_TEMPLATE,
)
from .helpers import _subentry_title

_WEATHER_CONDITIONS = [
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
]

# Sentinel option value for "add a new item" in manage lists. Must satisfy
# hassfest's translation-key rules ([a-z0-9-_]+, no leading/trailing _ or -).
_ACTION_ADD = "add"

# Behavior keys that a template can define and a cover can override.
# Activation flags (shade_enable, solar_gain_enable) are intentionally absent:
# they are always cover-specific and never inherited from a template.
_TEMPLATE_BEHAVIOR_KEYS: tuple[str, ...] = (
    "angle_left", "angle_right",
    "shade_distance", "shade_max_height", "shade_min_height",
    "shade_degrees", "shade_min_elevation", "shade_max_elevation",
    "shade_minimum_position", "shade_default_position",
    "shade_change_threshold", "shade_time_out",
    "solar_gain_position_solar", "solar_gain_position_cold",
)

# ── Behavior form: collapsible sections ─────────────────────────────────────────
# The cover behavior and template automation forms group ~16 fields into
# collapsible sections (HA `section`). Internally the rest of the code keeps a
# FLAT data model: _flatten_sections() unwraps the nested user_input on submit,
# and _build_section_schema(values=...) pre-fills field defaults on display.

def _num(lo: float, hi: float, unit: str, step: float | None = None) -> selector.NumberSelector:
    cfg = dict(min=lo, max=hi, mode="slider", unit_of_measurement=unit)
    if step is not None:
        cfg["step"] = step
    return selector.NumberSelector(selector.NumberSelectorConfig(**cfg))


# field -> (default, selector)
_BEHAVIOR_FIELDS: dict[str, tuple[Any, Any]] = {
    "angle_left":                (85,    _num(0, 90, "°")),
    "angle_right":               (85,    _num(0, 90, "°")),
    "shade_distance":            (0.4,   _num(0, 3, "m", 0.1)),
    "shade_max_height":          (1.8,   _num(0, 3, "m", 0.1)),
    "shade_min_height":          (0.0,   _num(0, 3, "m", 0.1)),
    "shade_degrees":             (90,    _num(0, 180, "°")),
    "shade_min_elevation":       (5,     _num(0, 90, "°")),
    "shade_max_elevation":       (90,    _num(0, 90, "°")),
    "shade_minimum_position":    (15,    _num(0, 100, "%")),
    "shade_default_position":    (100,   _num(0, 100, "%")),
    "shade_change_threshold":    (5,     _num(0, 50, "%")),
    "shade_time_out":            (2,     _num(0, 60, "min")),
    "solar_gain_position_solar": (100,   _num(0, 100, "%")),
    "solar_gain_position_cold":  (0,     _num(0, 100, "%")),
    "shade_enable":              (False, selector.BooleanSelector()),
    "solar_gain_enable":         (False, selector.BooleanSelector()),
}

# (section_key, (fields...)) — order matters for display.
# Themes: geometry = physical dimensions; detection = sun orientation/elevation;
# shading = autonomous shading behaviour; solar_gain = temperature positioning.
_COVER_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("geometry",   ("shade_distance", "shade_max_height", "shade_min_height")),
    ("detection",  ("angle_left", "angle_right", "shade_degrees", "shade_min_elevation", "shade_max_elevation")),
    ("shading",    ("shade_enable", "shade_minimum_position", "shade_default_position", "shade_change_threshold", "shade_time_out")),
    ("solar_gain", ("solar_gain_enable", "solar_gain_position_solar", "solar_gain_position_cold")),
)
_TEMPLATE_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("geometry",   ("shade_distance", "shade_max_height", "shade_min_height")),
    ("detection",  ("shade_degrees", "shade_min_elevation", "shade_max_elevation")),
    ("shading",    ("shade_minimum_position", "shade_default_position", "shade_change_threshold", "shade_time_out")),
    ("solar_gain", ("solar_gain_position_solar", "solar_gain_position_cold")),
)
# All behavior sections start collapsed to keep the form compact.
_COLLAPSED_SECTIONS = {"geometry", "detection", "shading", "solar_gain"}


def _build_section_schema(
    sections: tuple[tuple[str, tuple[str, ...]], ...],
    values: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build a sectioned schema. *values* (flat) pre-fills field defaults.

    Pre-filling via per-field defaults (rather than add_suggested_values_to_schema)
    keeps it robust: every field here is a slider or toggle that always carries a
    value, so the default is exactly what the form shows.
    """
    values = values or {}
    fields: dict[Any, Any] = {}
    for key, names in sections:
        inner: dict[Any, Any] = {}
        for name in names:
            default, sel = _BEHAVIOR_FIELDS[name]
            inner[vol.Optional(name, default=values.get(name, default))] = sel
        fields[vol.Required(key)] = section(
            vol.Schema(inner), {"collapsed": key in _COLLAPSED_SECTIONS}
        )
    return vol.Schema(fields)


def _flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Unwrap nested section dicts from user_input into one flat dict."""
    flat: dict[str, Any] = {}
    for key, val in user_input.items():
        if isinstance(val, dict):
            flat.update(val)
        else:
            flat[key] = val
    return flat

_DEFAULT_COLOR_HEX = "#FFFFFF"
_DEFAULT_COLOR_RGB = [255, 255, 255]


def _hex_to_rgb(hex_color: str) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[i:i+2], 16) for i in (0, 2, 4)]


def _rgb_to_hex(rgb: list[int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _find_singleton(
    hass: HomeAssistant,
    subentry_type: str,
) -> tuple[config_entries.ConfigEntry | None, Any]:
    """Find the singleton subentry for *subentry_type* across ALL domain entries.

    Searching every config entry for the domain ensures correctness even when
    HA has created multiple entries (e.g. one via YAML import + one via the UI)
    or when the flow manager's internally-tracked entry differs from
    ``async_entries(DOMAIN)[0]``.

    Returns ``(entry, subentry)`` when found, ``(None, None)`` otherwise.
    """
    first_empty: tuple[config_entries.ConfigEntry, Any] | None = None
    for entry in hass.config_entries.async_entries(DOMAIN):
        for sub in entry.subentries.values():
            if sub.subentry_type != subentry_type or "items" not in sub.data:
                continue
            if sub.data["items"]:
                # Non-empty singleton — return immediately (highest priority)
                return entry, sub
            if first_empty is None:
                # Remember first empty singleton as fallback
                first_empty = (entry, sub)
    # Fallback: return first empty singleton (or None if nothing found)
    return first_empty if first_empty is not None else (None, None)


def _update_singleton_in_place(
    flow: ConfigSubentryFlow,
    subentry_type: str,
    items: list[dict[str, Any]],
) -> None:
    """Immediately persist items into the singleton WITHOUT closing the flow.

    Only updates when the singleton already exists (items were loaded from it,
    so it must exist). Safe to call from any flow context.
    async_update_subentry calls entry._async_process_listeners() which fires
    add_update_listener → coordinator's _on_entry_updated handles the refresh.
    """
    entry, sub = _find_singleton(flow.hass, subentry_type)
    if entry and sub:
        _LOGGER.debug(
            "config_flow [%s] _update_singleton_in_place: updating subentry %s → %d item(s)",
            subentry_type, sub.subentry_id, len(items),
        )
        flow.hass.config_entries.async_update_subentry(
            entry, sub, data={"items": items}
        )
    else:
        _LOGGER.warning(
            "config_flow [%s] _update_singleton_in_place: singleton subentry not found — nothing updated",
            subentry_type,
        )


# ── Module helpers ─────────────────────────────────────────────────────────────

def _get_entry(flow: ConfigSubentryFlow) -> ConfigEntry | None:
    """Return the parent config entry — works in both create and reconfigure flows.

    Tries four strategies in order:
    1. flow._config_entry  — private attr set by HA's subentry flow manager
    2. flow.config_entry   — public property (some HA versions)
    3. flow.context["entry_id"] — injected by some HA versions
    4. subentry_id lookup  — for reconfigure flows (context has "subentry_id")
    5. async_entries(DOMAIN) — last resort; safe because cover_extender enforces
       a single config entry (async_step_user aborts if one already exists).
    """
    # 1. Private attribute set by HA's subentry flow manager
    entry = getattr(flow, "_config_entry", None)
    if entry is not None:
        return entry
    # 2. Public property (present in some HA versions)
    try:
        entry = flow.config_entry
        if entry is not None:
            return entry
    except AttributeError:
        pass
    # 3. entry_id in flow context (injected by some HA versions)
    entry_id = flow.context.get("entry_id")
    if entry_id:
        return flow.hass.config_entries.async_get_entry(entry_id)
    # 4. subentry_id in context (reconfigure flows) — walk entries to find owner
    subentry_id = flow.context.get("subentry_id")
    if subentry_id:
        for e in flow.hass.config_entries.async_entries(DOMAIN):
            if subentry_id in e.subentries:
                return e
    # 5. cover_extender only ever has one config entry — return it if present
    entries = flow.hass.config_entries.async_entries(DOMAIN)
    if entries:
        return entries[0]
    _LOGGER.warning(
        "config_flow _get_entry: cannot resolve parent config entry "
        "(flow_id=%s source=%s context_keys=%s)",
        flow.flow_id,
        flow.source,
        list(flow.context.keys()),
    )
    return None


def _reconfigure_data(flow: ConfigSubentryFlow) -> dict[str, Any]:
    """Return existing subentry data for individual-subentry reconfigure flows.

    Uses the same multi-strategy entry lookup as _get_entry so it works even
    when flow.config_entry is unavailable (varies by HA version).
    """
    subentry_id = (
        getattr(flow, "_subentry_id", None)
        or getattr(flow, "subentry_id", None)
        or flow.context.get("subentry_id")
    )
    if not subentry_id:
        return {}
    entry = _get_entry(flow)
    if entry is None:
        return {}
    sub = entry.subentries.get(subentry_id)
    return dict(sub.data) if sub else {}


def _names_from_hass(hass: HomeAssistant, subentry_type: str) -> list[str]:
    """Return item names for *subentry_type* across ALL domain config entries.

    Searches every entry so the result is correct even when multiple config
    entries exist (YAML import + UI setup) or when subentries are spread
    across more than one entry.
    """
    names: list[str] = []
    found_singleton = False
    for entry in hass.config_entries.async_entries(DOMAIN):
        for s in entry.subentries.values():
            if s.subentry_type != subentry_type:
                continue
            if "items" in s.data:
                found_singleton = True
                names.extend(
                    item["name"] for item in s.data.get("items", []) if item.get("name")
                )
    if found_singleton:
        # De-duplicate while preserving order (multiple subentries may repeat names)
        seen: set[str] = set()
        unique: list[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        return unique
    # Legacy individual-subentry format fallback
    for entry in hass.config_entries.async_entries(DOMAIN):
        for s in entry.subentries.values():
            if s.subentry_type == subentry_type and "name" in s.data:
                names.append(s.data["name"])
    return names


def _items_from_hass(hass: HomeAssistant, subentry_type: str) -> list[dict[str, Any]]:
    """Return item dicts for *subentry_type* across ALL domain config entries.

    Same lookup strategy as _names_from_hass (singleton format first, legacy
    individual subentries as fallback), de-duplicated by name.
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    found_singleton = False
    for entry in hass.config_entries.async_entries(DOMAIN):
        for s in entry.subentries.values():
            if s.subentry_type != subentry_type:
                continue
            if "items" in s.data:
                found_singleton = True
                for item in s.data.get("items", []):
                    if (name := item.get("name")) and name not in seen:
                        seen.add(name)
                        items.append(item)
    if found_singleton:
        return items
    for entry in hass.config_entries.async_entries(DOMAIN):
        for s in entry.subentries.values():
            if s.subentry_type == subentry_type and (name := s.data.get("name")):
                if name not in seen:
                    seen.add(name)
                    items.append(dict(s.data))
    return items


# ── Dynamic option labels ──────────────────────────────────────────────────────
# Manage lists and identity dropdowns build their option labels in code
# (usage counts, azimuth, mode markers), so they cannot go through a selector
# translation_key. The text fragments are fetched from the loaded translations
# instead (same approach as helpers._subentry_title) with English fallbacks.

_LABEL_FALLBACKS: dict[str, str] = {
    "covers":      "cover(s)",
    "modes":       "mode(s)",
    "lock":        "lock",
    "hidden":      "hidden",
    "auto_shade":  "auto shade",
    "solar_gain":  "solar gain",
    "no_facade":   "(no facade yet)",
    "no_template": "(no template yet)",
    "no_mode":     "(no mode yet)",
}


async def _ui_labels(hass: HomeAssistant) -> dict[str, str]:
    """Return translated label fragments for dynamically built options."""
    labels = dict(_LABEL_FALLBACKS)
    try:
        translations = await ha_translation.async_get_translations(
            hass, hass.config.language, "selector", {DOMAIN}
        )
    except Exception:
        return labels
    for group in ("item_labels", "mode_behavior"):
        prefix = f"component.{DOMAIN}.selector.{group}.options."
        for key, value in translations.items():
            if key.startswith(prefix):
                labels[key[len(prefix):]] = value
    return labels


def _usage_counts(hass: HomeAssistant) -> dict[str, dict[str, int]]:
    """Count how many covers reference each facade / template / mode (by name)."""
    counts: dict[str, dict[str, int]] = {"facade": {}, "template": {}, "mode": {}}
    _, sub = _find_singleton(hass, SUBENTRY_TYPE_COVER)
    for item in (sub.data.get("items", []) if sub else []):
        if facade := item.get("facade"):
            counts["facade"][facade] = counts["facade"].get(facade, 0) + 1
        if template := item.get("template"):
            counts["template"][template] = counts["template"].get(template, 0) + 1
        for mode in (item.get("modes") or {}):
            counts["mode"][mode] = counts["mode"].get(mode, 0) + 1
    return counts


def _with_usage(label: str, count: int, labels: dict[str, str], noun: str = "covers") -> str:
    """Append a usage-count suffix ("· 3 cover(s)") to *label* when count > 0."""
    return f"{label} · {count} {labels[noun]}" if count else label


def _cover_display(hass: HomeAssistant, item: dict[str, Any]) -> str:
    """Human-facing name of a cover item (friendly name, else entity_id)."""
    entity_id = item.get("entity_id", "")
    state = hass.states.get(entity_id)
    friendly = state.attributes.get("friendly_name") if state else None
    return friendly or entity_id


def _referencing_covers(hass: HomeAssistant, kind: str, name: str) -> list[str]:
    """Display names of the covers referencing facade / template / mode *name*."""
    _, sub = _find_singleton(hass, SUBENTRY_TYPE_COVER)
    out: list[str] = []
    for item in (sub.data.get("items", []) if sub else []):
        if kind == SUBENTRY_TYPE_FACADE:
            referenced = item.get("facade") == name
        elif kind == SUBENTRY_TYPE_TEMPLATE:
            referenced = item.get("template") == name
        else:
            referenced = name in (item.get("modes") or {})
        if referenced:
            out.append(_cover_display(hass, item))
    return out


def _validate_item_name(
    name: str, items: list[dict[str, Any]], skip_idx: int | None = None
) -> dict[str, str]:
    """Validate a facade / mode / template name: non-empty and unique."""
    if not name:
        return {"name": "name_required"}
    for i, item in enumerate(items):
        if i != skip_idx and item.get("name") == name:
            return {"name": "name_exists"}
    return {}


def _behavior_errors(flat: dict[str, Any]) -> dict[str, str]:
    """Cross-field checks on a flattened behavior / automation form."""
    if flat.get("shade_min_height", 0) > flat.get("shade_max_height", 3):
        return {"base": "min_height_above_max"}
    if flat.get("shade_min_elevation", 0) > flat.get("shade_max_elevation", 90):
        return {"base": "min_elevation_above_max"}
    return {}


# ── Per-cover mode position form (shared by cover and mode flows) ─────────────

def _mode_position_schema() -> vol.Schema:
    """Form for a NON-automation mode's per-cover position: Fixed / Entity / None.

    A `choose` selector shows the right input per choice:
      - Fixed  -> a % slider applied as the position,
      - Entity -> an input_number/number whose value drives the position live
                  (the coordinator tracks it via _handle_mode_entity_change),
      - None   -> no forced position (the cover stays in place; locks if a lock mode).
    Automation modes never reach this form (their position comes from the behavior).
    """
    return vol.Schema({
        vol.Required("position"): selector.selector({
            "choose": {
                "translation_key": "mode_position_choice",
                "choices": {
                    "fixed":  {"selector": {"number": {"min": 0, "max": 100, "mode": "slider", "unit_of_measurement": "%"}}},
                    "entity": {"selector": {"entity": {"domain": ["input_number", "number"]}}},
                    "none":   {"selector": {"constant": {"value": True}}},
                },
            }
        }),
    })


def _choice_to_mode_cfg(choice: dict[str, Any]) -> dict[str, Any]:
    """Convert a submitted `choose` value into the stored mode config."""
    active = choice.get("active_choice")
    if active == "fixed":
        return {"type": "fixed", "value": int(choice.get("fixed", 0))}
    if active == "entity" and choice.get("entity"):
        return {"type": "entity", "value": str(choice.get("entity")).strip()}
    return {"type": "auto"}  # "none" (or "entity" with nothing picked)


def _mode_cfg_to_choice(cfg: Any) -> dict[str, Any]:
    """Convert a stored mode config into a `choose` suggested value.

    Handles the current dict format and legacy raw values (int = fixed
    position, str = entity id, None = no forced position).
    """
    if isinstance(cfg, dict):
        cfg_type, value = cfg.get("type"), cfg.get("value")
    elif cfg is None:
        return {"active_choice": "none"}
    elif isinstance(cfg, (int, float)):
        cfg_type, value = "fixed", cfg
    else:
        cfg_type, value = "entity", cfg
    if cfg_type == "fixed":
        try:
            return {"active_choice": "fixed", "fixed": int(value or 0)}
        except (TypeError, ValueError):
            return {"active_choice": "none"}
    if cfg_type == "entity" and value:
        return {"active_choice": "entity", "entity": value}
    return {"active_choice": "none"}


# ── Singleton save helper ──────────────────────────────────────────────────────

def _singleton_save(
    flow: ConfigSubentryFlow,
    subentry_type: str,
    title: str,
    items: list[dict[str, Any]],
) -> config_entries.ConfigFlowResult:
    """Persist the items list into a singleton subentry.

    - If the singleton already exists: update it via async_update_subentry (works
      in both create and reconfigure contexts) then abort.
    - If no singleton exists and flow is a create flow: use async_create_entry.
    - If no singleton exists and flow is a reconfigure flow: convert the subentry
      being reconfigured into the new singleton via async_update_subentry then abort.
      (async_create_entry raises ValueError when source == "reconfigure".)

    HA calls entry._async_process_listeners() from both async_add_subentry and
    async_update_subentry, which fires add_update_listener → coordinator's
    _on_entry_updated is triggered automatically for every mutation.
    No explicit reload is needed here — scheduling one would race with
    async_create_entry result processing and corrupt subentry data.
    """
    _LOGGER.debug(
        "config_flow [%s] _singleton_save: source=%s items=%d",
        subentry_type,
        flow.source,
        len(items),
    )

    # ── Case 1: singleton already exists (search across ALL entries) ──────────
    existing_entry, existing = _find_singleton(flow.hass, subentry_type)
    if existing_entry and existing:
        _LOGGER.debug(
            "config_flow [%s] _singleton_save: Case 1 — updating existing singleton %s in entry %s",
            subentry_type, existing.subentry_id, existing_entry.entry_id,
        )
        flow.hass.config_entries.async_update_subentry(
            existing_entry, existing, title=title, data={"items": items}
        )
        return flow.async_abort(reason="reconfigure_successful")

    # ── Case 2: create flow, no singleton yet ─────────────────────────────────
    if flow.source != "reconfigure":
        _LOGGER.debug(
            "config_flow [%s] _singleton_save: Case 2 — creating new singleton subentry",
            subentry_type,
        )
        return flow.async_create_entry(title=title, data={"items": items})

    # ── Case 3: reconfigure flow, no singleton ────────────────────────────────
    # async_create_entry raises ValueError in reconfigure context.
    # Convert the subentry being reconfigured into the singleton.
    subentry_id = (
        getattr(flow, "_subentry_id", None)
        or flow.context.get("subentry_id")
    )
    _LOGGER.debug(
        "config_flow [%s] _singleton_save: Case 3 — converting reconfigure subentry %s into singleton",
        subentry_type, subentry_id,
    )
    if subentry_id:
        # Find which entry owns this subentry (strategy 4 from _get_entry)
        for e in flow.hass.config_entries.async_entries(DOMAIN):
            current = e.subentries.get(subentry_id)
            if current:
                flow.hass.config_entries.async_update_subentry(
                    e, current, title=title, data={"items": items}
                )
                break
    return flow.async_abort(reason="reconfigure_successful")


# ── Rename cascade ─────────────────────────────────────────────────────────────

def _propagate_rename(
    hass: HomeAssistant, kind: str, old: str, new: str
) -> None:
    """Propagate a facade / mode / template rename to every cover referencing it.

    Covers reference these by name, so renaming one would otherwise orphan the
    link (facade lookup fails, mode loses its icon/lock/behavior, template falls
    back to defaults). This rewrites the stale name in the cover singleton:
      - facade   → cover["facade"]
      - template → cover["template"]
      - mode     → key in cover["modes"] (order preserved)
    """
    if not new or old == new:
        return
    entry, sub = _find_singleton(hass, SUBENTRY_TYPE_COVER)
    if not entry or not sub:
        return
    items = [dict(it) for it in sub.data.get("items", [])]
    changed = False
    for it in items:
        if kind == SUBENTRY_TYPE_FACADE and it.get("facade") == old:
            it["facade"] = new
            changed = True
        elif kind == SUBENTRY_TYPE_TEMPLATE and it.get("template") == old:
            it["template"] = new
            changed = True
        elif kind == SUBENTRY_TYPE_MODE:
            modes = it.get("modes")
            if isinstance(modes, dict) and old in modes:
                it["modes"] = {(new if k == old else k): v for k, v in modes.items()}
                changed = True
    if changed:
        _LOGGER.debug(
            "config_flow: cascade rename %s '%s' -> '%s' across covers", kind, old, new
        )
        hass.config_entries.async_update_subentry(entry, sub, data={"items": items})


# ── Facade Flow (singleton) ────────────────────────────────────────────────────

class FacadeFlowHandler(ConfigSubentryFlow):
    """Manage facades as a singleton subentry containing an items list."""

    _items: list[dict[str, Any]]
    _edit_idx: int
    _blocked: tuple[str, list[str]]

    @staticmethod
    def _item_schema() -> vol.Schema:
        return vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("azimuth", default=180): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=360, mode="slider", unit_of_measurement="°"
                )
            ),
        })

    def _load_items(self) -> None:
        _, sub = _find_singleton(self.hass, SUBENTRY_TYPE_FACADE)
        self._items = list(sub.data.get("items", []) if sub else [])
        _LOGGER.debug(
            "config_flow [facade] _load_items: found singleton=%s, loaded %d item(s): %s",
            sub.subentry_id if sub else "None",
            len(self._items),
            [i.get("name") for i in self._items],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("config_flow [facade] async_step_user → loading items and showing manage")
        self._load_items()
        return await self.async_step_manage()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("config_flow [facade] async_step_reconfigure → loading items and showing manage")
        self._load_items()
        return await self.async_step_manage()

    async def async_step_manage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            action: str = user_input["action"]
            _LOGGER.debug("config_flow [facade] async_step_manage: action=%s", action)
            if action == _ACTION_ADD:
                return await self.async_step_add()
            if action.startswith("select:"):
                self._edit_idx = int(action.split(":", 1)[1])
                return await self.async_step_item()

        _LOGGER.debug("config_flow [facade] async_step_manage: showing form with %d item(s)", len(self._items))
        labels = await _ui_labels(self.hass)
        used = _usage_counts(self.hass)["facade"]
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add facade"}]
        for i, item in enumerate(self._items):
            label = f"{item['name']} ({float(item.get('azimuth', 180)):g}°)"
            options.append({
                "value": f"select:{i}",
                "label": _with_usage(label, used.get(item["name"], 0), labels),
            })

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="facade_manage")
                )
            }),
            description_placeholders={"count": str(len(self._items))},
        )

    async def async_step_item(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        item_name = self._items[self._edit_idx]["name"]
        _LOGGER.debug("config_flow [facade] async_step_item: showing menu for '%s'", item_name)
        return self.async_show_menu(
            step_id="item",
            menu_options=["edit", "delete"],
            description_placeholders={"name": item_name},
        )

    async def async_step_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        name = self._items[self._edit_idx].get("name", "")
        if users := _referencing_covers(self.hass, SUBENTRY_TYPE_FACADE, name):
            self._blocked = (name, users)
            return await self.async_step_delete_blocked()
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [facade] delete: removed '%s', %d item(s) remaining", removed.get("name"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_FACADE, self._items)
        return await self.async_step_manage()

    async def async_step_delete_blocked(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        name, users = self._blocked
        return self.async_show_menu(
            step_id="delete_blocked",
            menu_options=["manage"],
            description_placeholders={
                "name": name, "count": str(len(users)), "covers": ", ".join(users),
            },
        )

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = (user_input.get("name") or "").strip()
            errors = _validate_item_name(name, self._items)
            if not errors:
                _LOGGER.debug("config_flow [facade] async_step_add: adding '%s'", name)
                self._items.append({**user_input, "name": name})
                _LOGGER.debug("config_flow [facade] async_step_add: saving %d item(s)", len(self._items))
                return _singleton_save(self, SUBENTRY_TYPE_FACADE, await _subentry_title(self.hass, SUBENTRY_TYPE_FACADE), self._items)
        return self.async_show_form(
            step_id="add",
            data_schema=self.add_suggested_values_to_schema(
                self._item_schema(), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = (user_input.get("name") or "").strip()
            errors = _validate_item_name(name, self._items, skip_idx=self._edit_idx)
            if not errors:
                old_name = self._items[self._edit_idx].get("name")
                _LOGGER.debug("config_flow [facade] async_step_edit: updating index %d -> '%s'", self._edit_idx, name)
                self._items[self._edit_idx] = {**user_input, "name": name}
                _propagate_rename(self.hass, SUBENTRY_TYPE_FACADE, old_name, name)
                return _singleton_save(self, SUBENTRY_TYPE_FACADE, await _subentry_title(self.hass, SUBENTRY_TYPE_FACADE), self._items)
        return self.async_show_form(
            step_id="edit",
            data_schema=self.add_suggested_values_to_schema(
                self._item_schema(), user_input or self._items[self._edit_idx]
            ),
            errors=errors,
        )


# ── Mode Flow (singleton) ──────────────────────────────────────────────────────

class ModeFlowHandler(ConfigSubentryFlow):
    """Manage modes as a singleton subentry containing an items list."""

    _items: list[dict[str, Any]]
    _edit_idx: int
    _blocked: tuple[str, list[str]]
    _pos_active: bool
    _pos_covers: list[dict[str, Any]]
    _pos_targets: list[int]
    _pos_idx: int

    @staticmethod
    def _item_schema(values: dict[str, Any] | None = None) -> vol.Schema:
        """Mode form: name + collapsed "appearance" and "options" sections.

        *values* (flat, color as an RGB list) pre-fills field defaults, keeping
        only the name visible by default. Avoids the heavy full-width color row
        being shown up-front.
        """
        v = values or {}
        name_key = vol.Required("name", default=v["name"]) if v.get("name") else vol.Required("name")
        behavior_key = (
            vol.Optional("behavior", default=v["behavior"]) if v.get("behavior")
            else vol.Optional("behavior")
        )
        return vol.Schema({
            name_key: selector.TextSelector(),
            vol.Required("appearance"): section(
                vol.Schema({
                    vol.Optional("icon",  default=v.get("icon",  "mdi:help-circle")): selector.IconSelector(),
                    vol.Optional("color", default=v.get("color", _DEFAULT_COLOR_RGB)): selector.ColorRGBSelector(),
                }),
                {"collapsed": True},
            ),
            vol.Required("options"): section(
                vol.Schema({
                    vol.Optional("lock", default=v.get("lock", False)): selector.BooleanSelector(),
                    behavior_key: selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["auto_shade", "solar_gain"],
                            mode="dropdown",
                            translation_key="mode_behavior",
                        )
                    ),
                    vol.Optional("hidden", default=v.get("hidden", False)): selector.BooleanSelector(),
                }),
                {"collapsed": True},
            ),
        })

    def _load_items(self) -> None:
        _, sub = _find_singleton(self.hass, SUBENTRY_TYPE_MODE)
        self._items = list(sub.data.get("items", []) if sub else [])
        _LOGGER.debug(
            "config_flow [mode] _load_items: found singleton=%s, loaded %d item(s): %s",
            sub.subentry_id if sub else "None",
            len(self._items),
            [i.get("name") for i in self._items],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("config_flow [mode] async_step_user → loading items and showing manage")
        self._load_items()
        return await self.async_step_manage()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("config_flow [mode] async_step_reconfigure")
        self._load_items()
        return await self.async_step_manage()

    async def async_step_manage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            action: str = user_input["action"]
            _LOGGER.debug("config_flow [mode] async_step_manage: action=%s", action)
            if action == _ACTION_ADD:
                return await self.async_step_add()
            if action.startswith("select:"):
                self._edit_idx = int(action.split(":", 1)[1])
                return await self.async_step_item()

        _LOGGER.debug("config_flow [mode] async_step_manage: showing form with %d item(s)", len(self._items))
        labels = await _ui_labels(self.hass)
        used = _usage_counts(self.hass)["mode"]
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add mode"}]
        for i, item in enumerate(self._items):
            markers: list[str] = []
            if item.get("lock"):
                markers.append(labels["lock"])
            if behavior := item.get("behavior"):
                markers.append(labels.get(behavior, behavior))
            if item.get("hidden"):
                markers.append(labels["hidden"])
            label = item["name"]
            if markers:
                label += f" ({', '.join(markers)})"
            options.append({
                "value": f"select:{i}",
                "label": _with_usage(label, used.get(item["name"], 0), labels),
            })

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="mode_manage")
                )
            }),
            description_placeholders={"count": str(len(self._items))},
        )

    async def async_step_item(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        item = self._items[self._edit_idx]
        item_name = item["name"]
        _LOGGER.debug("config_flow [mode] async_step_item: showing menu for '%s'", item_name)
        # "Positions" only makes sense for a plain mode (automation modes have
        # computed positions) that is linked to at least one cover.
        menu_options = ["edit", "delete"]
        if not item.get("behavior") and _referencing_covers(
            self.hass, SUBENTRY_TYPE_MODE, item_name
        ):
            menu_options = ["edit", "positions", "delete"]
        return self.async_show_menu(
            step_id="item",
            menu_options=menu_options,
            description_placeholders={"name": item_name},
        )

    async def async_step_positions(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit this mode's position on every cover linking it, one per screen.

        Each screen is pre-filled with the cover's current value; the cover
        singleton is persisted once after the last screen.
        """
        mode_name = self._items[self._edit_idx]["name"]

        if user_input is None and not getattr(self, "_pos_active", False):
            # First entry from the item menu: snapshot covers and pick targets.
            _, sub = _find_singleton(self.hass, SUBENTRY_TYPE_COVER)
            self._pos_covers = [dict(it) for it in (sub.data.get("items", []) if sub else [])]
            self._pos_targets = [
                i for i, it in enumerate(self._pos_covers)
                if mode_name in (it.get("modes") or {})
            ]
            self._pos_idx = 0
            self._pos_active = True
            if not self._pos_targets:
                self._pos_active = False
                return await self.async_step_manage()

        if user_input is not None:
            idx = self._pos_targets[self._pos_idx]
            item = self._pos_covers[idx]
            modes = dict(item.get("modes", {}))
            modes[mode_name] = _choice_to_mode_cfg(user_input.get("position") or {})
            self._pos_covers[idx] = {**item, "modes": modes}
            self._pos_idx += 1

        if self._pos_idx >= len(self._pos_targets):
            self._pos_active = False
            _LOGGER.debug(
                "config_flow [mode] async_step_positions: saving '%s' positions on %d cover(s)",
                mode_name, len(self._pos_targets),
            )
            _update_singleton_in_place(self, SUBENTRY_TYPE_COVER, self._pos_covers)
            return await self.async_step_manage()

        target = self._pos_covers[self._pos_targets[self._pos_idx]]
        current = (target.get("modes") or {}).get(mode_name)
        schema = self.add_suggested_values_to_schema(
            _mode_position_schema(), {"position": _mode_cfg_to_choice(current)}
        )
        return self.async_show_form(
            step_id="positions",
            data_schema=schema,
            description_placeholders={
                "name": mode_name,
                "cover": _cover_display(self.hass, target),
                "index": str(self._pos_idx + 1),
                "total": str(len(self._pos_targets)),
            },
            last_step=(self._pos_idx >= len(self._pos_targets) - 1),
        )

    async def async_step_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        name = self._items[self._edit_idx].get("name", "")
        if users := _referencing_covers(self.hass, SUBENTRY_TYPE_MODE, name):
            self._blocked = (name, users)
            return await self.async_step_delete_blocked()
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [mode] delete: removed '%s', %d item(s) remaining", removed.get("name"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_MODE, self._items)
        return await self.async_step_manage()

    async def async_step_delete_blocked(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        name, users = self._blocked
        return self.async_show_menu(
            step_id="delete_blocked",
            menu_options=["manage"],
            description_placeholders={
                "name": name, "count": str(len(users)), "covers": ", ".join(users),
            },
        )

    @staticmethod
    def _ui_to_item(user_input: dict[str, Any]) -> dict[str, Any]:
        """Convert UI values (RGB list) to stored format (hex string)."""
        item = dict(user_input)
        if isinstance(item.get("color"), list):
            item["color"] = _rgb_to_hex(item["color"])
        return item

    @staticmethod
    def _item_to_ui(item: dict[str, Any]) -> dict[str, Any]:
        """Convert stored format (hex string) to UI values (RGB list)."""
        ui = dict(item)
        color = ui.get("color", _DEFAULT_COLOR_HEX)
        try:
            ui["color"] = _hex_to_rgb(color)
        except (ValueError, IndexError):
            ui["color"] = _DEFAULT_COLOR_RGB
        return ui

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        flat: dict[str, Any] | None = None
        if user_input is not None:
            flat = _flatten_sections(user_input)
            flat["name"] = (flat.get("name") or "").strip()
            errors = _validate_item_name(flat["name"], self._items)
            if not errors:
                _LOGGER.debug("config_flow [mode] async_step_add: adding '%s'", flat["name"])
                self._items.append(self._ui_to_item(flat))
                return _singleton_save(self, SUBENTRY_TYPE_MODE, await _subentry_title(self.hass, SUBENTRY_TYPE_MODE), self._items)
        return self.async_show_form(step_id="add", data_schema=self._item_schema(flat), errors=errors)

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        flat: dict[str, Any] | None = None
        if user_input is not None:
            flat = _flatten_sections(user_input)
            flat["name"] = (flat.get("name") or "").strip()
            errors = _validate_item_name(flat["name"], self._items, skip_idx=self._edit_idx)
            if not errors:
                old_name = self._items[self._edit_idx].get("name")
                _LOGGER.debug("config_flow [mode] async_step_edit: updating index %d -> '%s'", self._edit_idx, flat["name"])
                self._items[self._edit_idx] = self._ui_to_item(flat)
                _propagate_rename(self.hass, SUBENTRY_TYPE_MODE, old_name, flat["name"])
                return _singleton_save(self, SUBENTRY_TYPE_MODE, await _subentry_title(self.hass, SUBENTRY_TYPE_MODE), self._items)
        return self.async_show_form(
            step_id="edit",
            data_schema=self._item_schema(flat or self._item_to_ui(self._items[self._edit_idx])),
            errors=errors,
        )


# ── Template Flow (singleton, two-step wizard per item) ────────────────────────

class TemplateFlowHandler(ConfigSubentryFlow):
    """Manage cover templates as a singleton subentry containing an items list."""

    _items: list[dict[str, Any]]
    _edit_idx: int
    _blocked: tuple[str, list[str]]
    _pending_identity: dict[str, Any]

    @staticmethod
    def _identity_schema() -> vol.Schema:
        return vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("angle_left",  default=85): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=90, mode="slider", unit_of_measurement="°")
            ),
            vol.Required("angle_right", default=85): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=90, mode="slider", unit_of_measurement="°")
            ),
        })

    @staticmethod
    def _automation_schema(values: dict[str, Any] | None = None) -> vol.Schema:
        """Template automation form, grouped into collapsible sections."""
        return _build_section_schema(_TEMPLATE_SECTIONS, values)

    @staticmethod
    def _pack_automation(ui: dict[str, Any]) -> dict[str, Any]:
        return {
            "shade": {
                "distance":         ui.get("shade_distance",         0.4),
                "max_height":       ui.get("shade_max_height",       1.8),
                "min_height":       ui.get("shade_min_height",       0.0),
                "degrees":          ui.get("shade_degrees",          90),
                "min_elevation":    ui.get("shade_min_elevation",    5),
                "max_elevation":    ui.get("shade_max_elevation",    90),
                "minimum_position": ui.get("shade_minimum_position", 15),
                "default_position": ui.get("shade_default_position", 100),
                "change_threshold": ui.get("shade_change_threshold", 5),
                "time_out":         ui.get("shade_time_out",         2),
            },
            "solar_gain": {
                "position_solar": ui.get("solar_gain_position_solar", 100),
                "position_cold":  ui.get("solar_gain_position_cold",  0),
            },
        }

    @staticmethod
    def _flatten_automation(d: dict[str, Any]) -> dict[str, Any]:
        shade = d.get("shade", {})
        sg    = d.get("solar_gain", {})
        return {
            "shade_distance":            shade.get("distance",         0.4),
            "shade_max_height":          shade.get("max_height",       1.8),
            "shade_min_height":          shade.get("min_height",       0.0),
            "shade_degrees":             shade.get("degrees",          90),
            "shade_min_elevation":       shade.get("min_elevation",    5),
            "shade_max_elevation":       shade.get("max_elevation",    90),
            "shade_minimum_position":    shade.get("minimum_position", 15),
            "shade_default_position":    shade.get("default_position", 100),
            "shade_change_threshold":    shade.get("change_threshold", 5),
            "shade_time_out":            shade.get("time_out",         2),
            "solar_gain_position_solar": sg.get("position_solar",      100),
            "solar_gain_position_cold":  sg.get("position_cold",       0),
        }

    def _load_items(self) -> None:
        _, sub = _find_singleton(self.hass, SUBENTRY_TYPE_TEMPLATE)
        self._items = list(sub.data.get("items", []) if sub else [])
        _LOGGER.debug(
            "config_flow [template] _load_items: found singleton=%s, loaded %d item(s): %s",
            sub.subentry_id if sub else "None",
            len(self._items),
            [i.get("name") for i in self._items],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("config_flow [template] async_step_user → loading items and showing manage")
        self._load_items()
        return await self.async_step_manage()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("config_flow [template] async_step_reconfigure")
        self._load_items()
        return await self.async_step_manage()

    async def async_step_manage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            action: str = user_input["action"]
            _LOGGER.debug("config_flow [template] async_step_manage: action=%s", action)
            if action == _ACTION_ADD:
                return await self.async_step_add()
            if action.startswith("select:"):
                self._edit_idx = int(action.split(":", 1)[1])
                return await self.async_step_item()

        _LOGGER.debug("config_flow [template] async_step_manage: showing form with %d item(s)", len(self._items))
        labels = await _ui_labels(self.hass)
        used = _usage_counts(self.hass)["template"]
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add template"}]
        for i, item in enumerate(self._items):
            # Dimensions are what tells templates apart: height (range) and
            # obstacle distance, from the geometry section.
            shade = item.get("shade", {})
            max_h = float(shade.get("max_height", 1.8))
            min_h = float(shade.get("min_height", 0.0))
            dist = float(shade.get("distance", 0.4))
            height = f"H {min_h:g}-{max_h:g} m" if min_h else f"H {max_h:g} m"
            label = f"{item['name']} ({height} · D {dist:g} m)"
            options.append({
                "value": f"select:{i}",
                "label": _with_usage(label, used.get(item["name"], 0), labels),
            })

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="template_manage")
                )
            }),
            description_placeholders={"count": str(len(self._items))},
        )

    async def async_step_item(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        item_name = self._items[self._edit_idx]["name"]
        _LOGGER.debug("config_flow [template] async_step_item: showing menu for '%s'", item_name)
        return self.async_show_menu(
            step_id="item",
            menu_options=["edit", "delete"],
            description_placeholders={"name": item_name},
        )

    async def async_step_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        name = self._items[self._edit_idx].get("name", "")
        if users := _referencing_covers(self.hass, SUBENTRY_TYPE_TEMPLATE, name):
            self._blocked = (name, users)
            return await self.async_step_delete_blocked()
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [template] delete: removed '%s', %d item(s) remaining", removed.get("name"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_TEMPLATE, self._items)
        return await self.async_step_manage()

    async def async_step_delete_blocked(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        name, users = self._blocked
        return self.async_show_menu(
            step_id="delete_blocked",
            menu_options=["manage"],
            description_placeholders={
                "name": name, "count": str(len(users)), "covers": ", ".join(users),
            },
        )

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = (user_input.get("name") or "").strip()
            errors = _validate_item_name(name, self._items)
            if not errors:
                _LOGGER.debug("config_flow [template] async_step_add: identity '%s'", name)
                self._pending_identity = {**user_input, "name": name}
                return await self.async_step_add_automation()
        return self.async_show_form(
            step_id="add",
            data_schema=self.add_suggested_values_to_schema(
                self._identity_schema(), user_input or {}
            ),
            errors=errors,
            last_step=False,
        )

    async def async_step_add_automation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        flat: dict[str, Any] | None = None
        if user_input is not None:
            flat = _flatten_sections(user_input)
            errors = _behavior_errors(flat)
            if not errors:
                self._items.append({**self._pending_identity, **self._pack_automation(flat)})
                _LOGGER.debug("config_flow [template] async_step_add_automation: saving %d item(s)", len(self._items))
                return _singleton_save(self, SUBENTRY_TYPE_TEMPLATE, await _subentry_title(self.hass, SUBENTRY_TYPE_TEMPLATE), self._items)
        return self.async_show_form(
            step_id="add_automation", data_schema=self._automation_schema(flat), errors=errors
        )

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing = self._items[self._edit_idx]
        errors: dict[str, str] = {}
        if user_input is not None:
            name = (user_input.get("name") or "").strip()
            errors = _validate_item_name(name, self._items, skip_idx=self._edit_idx)
            if not errors:
                _LOGGER.debug("config_flow [template] async_step_edit: identity '%s' at index %d", name, self._edit_idx)
                self._pending_identity = {**user_input, "name": name}
                return await self.async_step_edit_automation()
        identity = user_input or {
            k: existing[k] for k in ("name", "angle_left", "angle_right") if k in existing
        }
        return self.async_show_form(
            step_id="edit",
            data_schema=self.add_suggested_values_to_schema(self._identity_schema(), identity),
            errors=errors,
            last_step=False,
        )

    async def async_step_edit_automation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing = self._items[self._edit_idx]
        errors: dict[str, str] = {}
        flat: dict[str, Any] | None = None
        if user_input is not None:
            flat = _flatten_sections(user_input)
            errors = _behavior_errors(flat)
            if not errors:
                old_name = existing.get("name")
                self._items[self._edit_idx] = {**self._pending_identity, **self._pack_automation(flat)}
                _propagate_rename(self.hass, SUBENTRY_TYPE_TEMPLATE, old_name, self._pending_identity.get("name"))
                _LOGGER.debug("config_flow [template] async_step_edit_automation: saving %d item(s)", len(self._items))
                return _singleton_save(self, SUBENTRY_TYPE_TEMPLATE, await _subentry_title(self.hass, SUBENTRY_TYPE_TEMPLATE), self._items)
        return self.async_show_form(
            step_id="edit_automation",
            data_schema=self._automation_schema(flat or self._flatten_automation(existing)),
            errors=errors,
        )


# ── Global Settings Flow (singleton subentry) ─────────────────────────────────

class GlobalFlowHandler(ConfigSubentryFlow):
    """Manage global Cover Extender settings as a singleton subentry."""

    def _schema(self, values: dict[str, Any] | None = None) -> vol.Schema:
        """Global settings.

        command_interval is top-level; display toggles and solar-gain settings are
        grouped into collapsed sections. The solar-gain temperature threshold is an
        input_number/number entity (no fixed value) — a plain EntitySelector, so it
        lives inside the section and pre-fills reliably (unlike a `choose`). When
        unset, the coordinator falls back to 19 °C.
        """
        v = values or {}

        def opt(key: str, default: Any = None):
            return vol.Optional(key, default=default) if default is not None else vol.Optional(key)

        def _is_num(x: Any) -> bool:
            try:
                float(x)
                return True
            except (TypeError, ValueError):
                return False

        # Threshold is an input_number/number entity. Only pre-fill the picker when
        # the stored value actually looks like an entity id (ignore legacy numbers).
        raw_thr = v.get("sg_temperature_threshold")
        thr_ent = raw_thr if (isinstance(raw_thr, str) and not _is_num(raw_thr)) else None

        display = {
            vol.Optional("show_sun_facing", default=v.get("show_sun_facing", True)):  selector.BooleanSelector(),
            vol.Optional("show_auto_shade", default=v.get("show_auto_shade", True)):  selector.BooleanSelector(),
            vol.Optional("show_solar_gain", default=v.get("show_solar_gain", False)): selector.BooleanSelector(),
        }
        solar_gain = {
            opt("sg_temperature_entity", v.get("sg_temperature_entity")):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            opt("sg_temperature_threshold", thr_ent):
                selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_number", "number"])),
            opt("sg_weather_entity", v.get("sg_weather_entity")):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            vol.Optional("sg_good_conditions", default=v.get("sg_good_conditions", ["sunny", "partlycloudy"])):
                selector.SelectSelector(selector.SelectSelectorConfig(options=_WEATHER_CONDITIONS, multiple=True, mode="dropdown")),
        }
        return vol.Schema({
            vol.Required("command_interval", default=v.get("command_interval", DEFAULT_COMMAND_INTERVAL_MS)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=5000, step=100, mode="box", unit_of_measurement="ms")),
            vol.Required("display"):    section(vol.Schema(display), {"collapsed": True}),
            vol.Required("solar_gain"): section(vol.Schema(solar_gain), {"collapsed": True}),
        })

    def _store_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Flatten the sectioned form into the flat storage shape."""
        return _flatten_sections(user_input)

    def _find_existing(self) -> tuple | tuple[None, None]:
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            for sub in entry.subentries.values():
                if sub.subentry_type == SUBENTRY_TYPE_GLOBAL:
                    return entry, sub
        return None, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing_entry, existing = self._find_existing()
        if existing_entry and existing:
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            return self.async_create_entry(
                title=await _subentry_title(self.hass, SUBENTRY_TYPE_GLOBAL),
                data=self._store_data(user_input),
            )
        return self.async_show_form(step_id="user", data_schema=self._schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            existing_entry, existing = self._find_existing()
            if existing_entry and existing:
                self.hass.config_entries.async_update_subentry(
                    existing_entry, existing, data=self._store_data(user_input)
                )
            return self.async_abort(reason="reconfigure_successful")
        existing_entry, existing = self._find_existing()
        current = dict(existing.data) if existing else {}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(current),
        )


# ── Cover Flow (singleton, 3-step wizard per item) ────────────────────────────

class CoverFlowHandler(ConfigSubentryFlow):
    """Manage covers as a singleton subentry containing an items list.

    Add wizard (3 steps):
      Step 1 (add):           entity_id, entity_picture, facade, template, exclusion
      Step 2 (add_behavior):  angles + shade/solar-gain params + activation
      Step 3 (add_modes):     link modes, then a position per NEW non-automation mode

    Edit wizard (2 steps): identity then behavior only. Modes are managed by the
    dedicated "link modes" action (async_step_modes) to avoid duplication.
    """

    _items: list[dict[str, Any]]
    _edit_idx: int
    _pending_identity: dict[str, Any]
    _pending_behavior: dict[str, Any]
    _pending_modes_selected: list[str]
    _pending_modes_existing: dict[str, Any]
    _modes_to_prompt: list[str]
    _pending_modes_result: dict[str, Any]
    _mode_pos_idx: int
    _modes_flow_kind: str  # "add" | "edit" | "shortcut"

    def _load_items(self) -> None:
        _, sub = _find_singleton(self.hass, SUBENTRY_TYPE_COVER)
        self._items = list(sub.data.get("items", []) if sub else [])
        _LOGGER.debug(
            "config_flow [cover] _load_items: found singleton=%s, loaded %d item(s)",
            sub.subentry_id if sub else "None",
            len(self._items),
        )

    # ── Step-1 schema ──────────────────────────────────────────────────────────

    def _identity_schema(self, labels: dict[str, str]) -> vol.Schema:
        facades = sorted(
            _items_from_hass(self.hass, SUBENTRY_TYPE_FACADE),
            key=lambda item: str(item.get("name", "")).casefold(),
        )
        facade_options: list[dict[str, str]] = [
            {
                "value": item["name"],
                "label": f"{item['name']} ({float(item.get('azimuth', 180)):g}°)",
            }
            for item in facades
        ] or [{"value": "", "label": labels["no_facade"]}]
        templates = sorted(
            _names_from_hass(self.hass, SUBENTRY_TYPE_TEMPLATE), key=str.casefold
        )
        template_options: list[dict[str, str]] = [
            {"value": name, "label": name} for name in templates
        ] or [{"value": "", "label": labels["no_template"]}]
        return vol.Schema({
            vol.Required("entity_id"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="cover")
            ),
            vol.Optional("entity_picture"): selector.TextSelector(),
            vol.Required("facade"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=facade_options, mode="dropdown")
            ),
            vol.Optional("template"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=template_options, mode="dropdown")
            ),
            vol.Optional("exclusion"): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
        })

    # ── Step-2 schema ──────────────────────────────────────────────────────────

    @staticmethod
    def _behavior_schema(values: dict[str, Any] | None = None) -> vol.Schema:
        """Cover behavior form, grouped into collapsible sections."""
        return _build_section_schema(_COVER_SECTIONS, values)

    # ── Step-3 helpers (modes) ────────────────────────────────────────────────

    def _modes_select_schema(self, labels: dict[str, str]) -> vol.Schema:
        """Multiselect: choose which modes apply to this cover.

        Labels carry the mode's lock / automation-behavior markers so the
        choice is informed without opening each mode. Definition order is kept
        (it drives the mode selector entity's option order).
        """
        mode_options: list[dict[str, str]] = []
        for item in _items_from_hass(self.hass, SUBENTRY_TYPE_MODE):
            markers: list[str] = []
            if item.get("lock"):
                markers.append(labels["lock"])
            if behavior := item.get("behavior"):
                markers.append(labels.get(behavior, behavior))
            label = item["name"]
            if markers:
                label += f" ({', '.join(markers)})"
            mode_options.append({"value": item["name"], "label": label})
        return vol.Schema({
            vol.Optional("selected_modes", default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=mode_options or [{"value": "", "label": labels["no_mode"]}],
                    multiple=True,
                    mode="list",
                )
            )
        })

    def _mode_behavior(self, mode_name: str) -> str | None:
        """Return the behavior (auto_shade / solar_gain / None) of a mode by name.

        Behavior lives on the mode (shared across covers); the per-cover position
        only matters for modes that have no behavior.
        """
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            for s in entry.subentries.values():
                if s.subentry_type != SUBENTRY_TYPE_MODE or "items" not in s.data:
                    continue
                for item in s.data["items"]:
                    if item.get("name") == mode_name:
                        return item.get("behavior") or None
        return None

    @staticmethod
    def _modes_selected_from_data(stored_modes: dict[str, Any]) -> list[str]:
        """Return list of mode names present in stored cover modes."""
        return list(stored_modes.keys())

    # ── Per-mode position loop (shared by add / edit / shortcut) ───────────────

    async def async_step_mode_position(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask the per-cover position for each queued plain mode, one per screen.

        Modes in self._modes_to_prompt are asked (non-automation): every
        selected one in the link-modes shortcut (pre-filled with the stored
        value so it can be edited), only the new ones in the add wizard.
        Automation modes (auto_shade / solar_gain) have a known "auto" value
        and are merged in _finalize_modes with no screen.
        """
        to_prompt = self._modes_to_prompt

        # Record the answer for the mode just shown, then advance.
        if user_input is not None:
            name = to_prompt[self._mode_pos_idx]
            self._pending_modes_result[name] = _choice_to_mode_cfg(
                user_input.get("position") or {}
            )
            self._mode_pos_idx += 1

        # No (more) modes to process -> finalize.
        if self._mode_pos_idx >= len(to_prompt):
            return await self._finalize_modes()

        # Plain mode -> editable form, pre-filled with the stored value if any.
        name = to_prompt[self._mode_pos_idx]
        schema = _mode_position_schema()
        if (existing := self._pending_modes_existing.get(name)) is not None:
            schema = self.add_suggested_values_to_schema(
                schema, {"position": _mode_cfg_to_choice(existing)}
            )
        return self.async_show_form(
            step_id="mode_position",
            data_schema=schema,
            description_placeholders={
                "name": name,
                "cover": self._current_cover_label(),
                "index": str(self._mode_pos_idx + 1),
                "total": str(len(to_prompt)),
            },
            last_step=(self._mode_pos_idx >= len(to_prompt) - 1),
        )

    async def _finalize_modes(self) -> config_entries.ConfigFlowResult:
        """Merge existing + newly-collected modes into the cover item and persist.

        Order follows the multiselect; each selected mode resolves to its freshly
        prompted value (new plain mode), its previously stored value (already-linked
        mode), or {"type": "auto"} (new automation mode).
        """
        modes: dict[str, Any] = {}
        for name in self._pending_modes_selected:
            if name in self._pending_modes_result:
                modes[name] = self._pending_modes_result[name]
            elif name in self._pending_modes_existing:
                modes[name] = self._pending_modes_existing[name]
            else:  # new automation mode -> known value
                modes[name] = {"type": "auto"}

        if self._modes_flow_kind == "add":
            self._items.append({
                **self._pending_identity, **self._pending_behavior, "modes": modes,
            })
        elif self._modes_flow_kind == "edit":
            self._items[self._edit_idx] = {
                **self._pending_identity, **self._pending_behavior, "modes": modes,
            }
        else:  # "shortcut" - keep identity/behavior untouched
            self._items[self._edit_idx] = {
                **self._items[self._edit_idx], "modes": modes,
            }
        _LOGGER.debug("config_flow [cover] _finalize_modes (%s): %d mode(s)", self._modes_flow_kind, len(modes))
        return _singleton_save(
            self, SUBENTRY_TYPE_COVER,
            await _subentry_title(self.hass, SUBENTRY_TYPE_COVER),
            self._items,
        )

    def _begin_mode_positions(self, selected: list[str], kind: str) -> None:
        """Initialise the per-mode position loop state.

        Non-automation modes are queued for a position prompt. In the
        link-modes shortcut EVERY selected one is asked (pre-filled with its
        stored value, so positions are editable in place); in the add wizard
        they are all new anyway. Automation modes are always auto.
        """
        self._pending_modes_selected = selected
        self._pending_modes_existing = (
            {} if kind == "add"
            else dict(self._items[self._edit_idx].get("modes", {}))
        )
        self._modes_to_prompt = [
            name for name in selected
            if self._mode_behavior(name) not in ("auto_shade", "solar_gain")
        ]
        self._pending_modes_result = {}
        self._mode_pos_idx = 0
        self._modes_flow_kind = kind

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_template_item(self, template_name: str) -> dict[str, Any]:
        """Return template item dict by name, or empty dict if not found."""
        if not template_name:
            return {}
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            for s in entry.subentries.values():
                if s.subentry_type != SUBENTRY_TYPE_TEMPLATE or "items" not in s.data:
                    continue
                for item in s.data["items"]:
                    if item.get("name") == template_name:
                        return item
        return {}

    @staticmethod
    def _behavior_defaults_from_template(tpl: dict[str, Any]) -> dict[str, Any]:
        """Extract behavior defaults from a template item for step-2 pre-fill."""
        shade = tpl.get("shade", {})
        sg    = tpl.get("solar_gain", {})
        return {
            "shade_enable":              False,
            "solar_gain_enable":         False,
            "angle_left":                tpl.get("angle_left",              85),
            "angle_right":               tpl.get("angle_right",             85),
            "shade_distance":            shade.get("distance",              0.4),
            "shade_max_height":          shade.get("max_height",            1.8),
            "shade_min_height":          shade.get("min_height",            0.0),
            "shade_degrees":             shade.get("degrees",               90),
            "shade_min_elevation":       shade.get("min_elevation",         5),
            "shade_max_elevation":       shade.get("max_elevation",         90),
            "shade_minimum_position":    shade.get("minimum_position",      15),
            "shade_default_position":    shade.get("default_position",      100),
            "shade_change_threshold":    shade.get("change_threshold",      5),
            "shade_time_out":            shade.get("time_out",              2),
            "solar_gain_position_solar": sg.get("position_solar",           100),
            "solar_gain_position_cold":  sg.get("position_cold",            0),
        }

    @staticmethod
    def _behavior_values_from_cover(d: dict[str, Any]) -> dict[str, Any]:
        """Extract behavior values from stored cover data for step-2 pre-fill.

        Handles both new (flat) and old (nested shade/solar_gain) formats.
        """
        shade = d.get("shade", {})
        sg    = d.get("solar_gain", {})
        return {
            "shade_enable":              d.get("shade_enable",              shade.get("enable",           False)),
            "solar_gain_enable":         d.get("solar_gain_enable",         sg.get("enable",              False)),
            "angle_left":                d.get("angle_left",                85),
            "angle_right":               d.get("angle_right",               85),
            "shade_distance":            d.get("shade_distance",            shade.get("distance",         0.4)),
            "shade_max_height":          d.get("shade_max_height",          shade.get("max_height",       1.8)),
            "shade_min_height":          d.get("shade_min_height",          shade.get("min_height",       0.0)),
            "shade_degrees":             d.get("shade_degrees",             shade.get("degrees",          90)),
            "shade_min_elevation":       d.get("shade_min_elevation",       shade.get("min_elevation",    5)),
            "shade_max_elevation":       d.get("shade_max_elevation",       shade.get("max_elevation",    90)),
            "shade_minimum_position":    d.get("shade_minimum_position",    shade.get("minimum_position", 15)),
            "shade_default_position":    d.get("shade_default_position",    shade.get("default_position", 100)),
            "shade_change_threshold":    d.get("shade_change_threshold",    shade.get("change_threshold", 5)),
            "shade_time_out":            d.get("shade_time_out",            shade.get("time_out",         2)),
            "solar_gain_position_solar": d.get("solar_gain_position_solar", sg.get("position_solar",     100)),
            "solar_gain_position_cold":  d.get("solar_gain_position_cold",  sg.get("position_cold",      0)),
        }

    def _behavior_prefill(self, cover_data: dict[str, Any]) -> dict[str, Any]:
        """Build pre-fill values for the behavior form.

        Priority: stored cover overrides → template defaults → schema defaults.
        Handles both the new flat format and the old nested shade/solar_gain format.
        """
        tpl_name = cover_data.get("template", "")
        tpl = self._get_template_item(tpl_name) if tpl_name else {}
        # Start from template defaults (gives correct base when no cover override exists)
        base = self._behavior_defaults_from_template(tpl) if tpl else {}
        # Layer stored cover overrides (only keys actually present in cover data)
        for key in _TEMPLATE_BEHAVIOR_KEYS:
            if key in cover_data:
                base[key] = cover_data[key]
        # Activation flags: cover-specific, handle both flat and legacy nested formats
        shade = cover_data.get("shade", {})
        sg    = cover_data.get("solar_gain", {})
        base["shade_enable"]      = cover_data.get("shade_enable",      shade.get("enable", False))
        base["solar_gain_enable"] = cover_data.get("solar_gain_enable", sg.get("enable",    False))
        return base

    @staticmethod
    def _strip_template_defaults(
        behavior: dict[str, Any],
        tpl: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove behavior values that match the template — keep only true overrides.

        Activation flags (shade_enable, solar_gain_enable) are always kept because
        they are cover-specific and have no template counterpart.
        If *tpl* is empty (no template selected) the dict is returned unchanged.
        """
        if not tpl:
            return behavior
        tpl_vals = CoverFlowHandler._behavior_defaults_from_template(tpl)
        result: dict[str, Any] = {}
        for key, val in behavior.items():
            if key in ("shade_enable", "solar_gain_enable"):
                result[key] = val  # always keep activation flags
            elif key not in tpl_vals or val != tpl_vals[key]:
                result[key] = val  # keep only if different from template
            # else: matches template → omit (template value applies at runtime)
        return result

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _cover_label(self, item: dict[str, Any]) -> str:
        """Return display label for a cover item in the manage list."""
        entity_id = item.get("entity_id", "")
        state = self.hass.states.get(entity_id)
        friendly = state.attributes.get("friendly_name") if state else None
        return f"{friendly} ({entity_id})" if friendly else entity_id

    def _current_cover_label(self) -> str:
        """Label of the cover currently being added/edited, for step titles.

        Prefers the in-progress identity (add flow, or an edit that changed the
        entity_id) and falls back to the stored item being edited.
        """
        entity_id = ""
        pending = getattr(self, "_pending_identity", None)
        if pending:
            entity_id = pending.get("entity_id", "")
        if not entity_id and getattr(self, "_edit_idx", None) is not None:
            try:
                entity_id = self._items[self._edit_idx].get("entity_id", "")
            except (IndexError, AttributeError):
                entity_id = ""
        if not entity_id:
            return ""
        state = self.hass.states.get(entity_id)
        friendly = state.attributes.get("friendly_name") if state else None
        return f"{friendly} ({entity_id})" if friendly else entity_id

    # ── Entry points ───────────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._load_items()
        return await self.async_step_manage()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._load_items()
        return await self.async_step_manage()

    # ── Manage step ────────────────────────────────────────────────────────────

    async def async_step_manage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            action: str = user_input["action"]
            _LOGGER.debug("config_flow [cover] async_step_manage: action=%s", action)
            if action == _ACTION_ADD:
                return await self.async_step_add()
            if action.startswith("select:"):
                self._edit_idx = int(action.split(":", 1)[1])
                return await self.async_step_item()

        _LOGGER.debug("config_flow [cover] async_step_manage: showing form with %d item(s)", len(self._items))
        labels = await _ui_labels(self.hass)
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add cover"}]
        for i, item in enumerate(self._items):
            extras: list[str] = []
            if facade := item.get("facade"):
                extras.append(facade)
            if template := item.get("template"):
                extras.append(template)
            if mode_count := len(item.get("modes") or {}):
                extras.append(f"{mode_count} {labels['modes']}")
            label = self._cover_label(item)
            if extras:
                label += " · " + " · ".join(extras)
            options.append({"value": f"select:{i}", "label": label})

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="cover_manage")
                )
            }),
            description_placeholders={"count": str(len(self._items))},
        )

    async def async_step_item(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        item = self._items[self._edit_idx]
        _LOGGER.debug("config_flow [cover] async_step_item: showing menu for '%s'", item.get("entity_id"))
        return self.async_show_menu(
            step_id="item",
            menu_options=["edit", "modes", "delete"],
            description_placeholders={"name": self._cover_label(item)},
        )

    # ── Modes-only shortcut (skip identity/behavior) ───────────────────────────

    async def async_step_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Shortcut from the item menu: edit ONLY the modes of an existing cover.

        Unlike the full edit wizard, identity and behavior are left untouched —
        the existing item dict is preserved and only its "modes" key is replaced.
        """
        existing = self._items[self._edit_idx]
        if user_input is not None:
            self._begin_mode_positions(user_input.get("selected_modes", []), "shortcut")
            _LOGGER.debug("config_flow [cover] async_step_modes: selected=%s", self._pending_modes_selected)
            return await self.async_step_mode_position()
        pre_selected = self._modes_selected_from_data(existing.get("modes", {}))
        return self.async_show_form(
            step_id="modes",
            data_schema=self.add_suggested_values_to_schema(
                self._modes_select_schema(await _ui_labels(self.hass)),
                {"selected_modes": pre_selected},
            ),
            description_placeholders={"cover": self._current_cover_label()},
            last_step=False,
        )

    async def async_step_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [cover] delete: removed '%s', %d item(s) remaining", removed.get("entity_id"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_COVER, self._items)
        return await self.async_step_manage()

    # ── Add flow (3 steps) ─────────────────────────────────────────────────────

    def _stamp_registry_id(self, identity: dict[str, Any]) -> dict[str, Any]:
        """Attach the cover's immutable registry id to the identity dict.

        The runtime resolves entity_registry_id → current entity_id, so a
        renamed cover keeps working. Covers without a registry entry keep the
        legacy entity_id-only behaviour.
        """
        identity = dict(identity)
        reg = er.async_get(self.hass).async_get(identity.get("entity_id", ""))
        if reg:
            identity["entity_registry_id"] = reg.id
        else:
            identity.pop("entity_registry_id", None)
        return identity

    def _identity_errors(
        self, user_input: dict[str, Any], skip_idx: int | None = None
    ) -> dict[str, str]:
        """Validate a cover identity form: unique entity, facade selected."""
        errors: dict[str, str] = {}
        entity_id = user_input.get("entity_id")
        for i, item in enumerate(self._items):
            if i != skip_idx and item.get("entity_id") == entity_id:
                errors["entity_id"] = "cover_exists"
                break
        if not user_input.get("facade"):
            errors["facade"] = "facade_required"
        return errors

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._identity_errors(user_input)
            if not errors:
                _LOGGER.debug("config_flow [cover] async_step_add: identity '%s'", user_input.get("entity_id"))
                self._pending_identity = self._stamp_registry_id(user_input)
                return await self.async_step_add_behavior()
        elif not _names_from_hass(self.hass, SUBENTRY_TYPE_FACADE):
            return self.async_abort(reason="no_facades")
        return self.async_show_form(
            step_id="add",
            data_schema=self.add_suggested_values_to_schema(
                self._identity_schema(await _ui_labels(self.hass)), user_input or {}
            ),
            errors=errors,
            last_step=False,
        )

    async def async_step_add_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        tpl = self._get_template_item(self._pending_identity.get("template", ""))
        errors: dict[str, str] = {}
        flat: dict[str, Any] | None = None
        if user_input is not None:
            flat = _flatten_sections(user_input)
            errors = _behavior_errors(flat)
            if not errors:
                _LOGGER.debug("config_flow [cover] async_step_add_behavior: behavior saved, going to modes")
                self._pending_behavior = self._strip_template_defaults(flat, tpl)
                return await self.async_step_add_modes()
        defaults = flat or (self._behavior_defaults_from_template(tpl) if tpl else None)
        return self.async_show_form(
            step_id="add_behavior",
            data_schema=self._behavior_schema(defaults),
            description_placeholders={"cover": self._current_cover_label()},
            errors=errors,
            last_step=False,
        )

    async def async_step_add_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 3a — choose which modes apply to this cover."""
        if user_input is not None:
            self._begin_mode_positions(user_input.get("selected_modes", []), "add")
            _LOGGER.debug("config_flow [cover] async_step_add_modes: selected=%s", self._pending_modes_selected)
            return await self.async_step_mode_position()
        return self.async_show_form(
            step_id="add_modes",
            data_schema=self._modes_select_schema(await _ui_labels(self.hass)),
            description_placeholders={"cover": self._current_cover_label()},
            last_step=False,
        )

    # ── Edit flow (3 steps) ────────────────────────────────────────────────────

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing = self._items[self._edit_idx]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._identity_errors(user_input, skip_idx=self._edit_idx)
            if not errors:
                _LOGGER.debug("config_flow [cover] async_step_edit: identity '%s'", user_input.get("entity_id"))
                self._pending_identity = self._stamp_registry_id(user_input)
                return await self.async_step_edit_behavior()
        identity_keys = ("entity_id", "entity_picture", "facade", "template", "exclusion")
        identity = user_input or {k: existing[k] for k in identity_keys if k in existing}
        return self.async_show_form(
            step_id="edit",
            data_schema=self.add_suggested_values_to_schema(
                self._identity_schema(await _ui_labels(self.hass)), identity
            ),
            description_placeholders={"cover": self._current_cover_label()},
            errors=errors,
            last_step=False,
        )

    async def async_step_edit_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing = self._items[self._edit_idx]
        # Template from the NEW identity (user may have changed it in step 1)
        tpl = self._get_template_item(self._pending_identity.get("template", ""))
        errors: dict[str, str] = {}
        flat: dict[str, Any] | None = None
        if user_input is not None:
            flat = _flatten_sections(user_input)
            errors = _behavior_errors(flat)
            if not errors:
                self._pending_behavior = self._strip_template_defaults(flat, tpl)
                # Modes are managed by the dedicated "link modes" action, not re-walked
                # here (that would duplicate it). Preserve the existing modes untouched.
                self._items[self._edit_idx] = {
                    **self._pending_identity,
                    **self._pending_behavior,
                    "modes": existing.get("modes", {}),
                }
                _LOGGER.debug("config_flow [cover] async_step_edit_behavior: identity+behavior saved, modes untouched")
                return _singleton_save(
                    self, SUBENTRY_TYPE_COVER,
                    await _subentry_title(self.hass, SUBENTRY_TYPE_COVER),
                    self._items,
                )
        # Pre-fill: template defaults + stored cover overrides
        defaults = flat or self._behavior_prefill(existing)
        return self.async_show_form(
            step_id="edit_behavior",
            data_schema=self._behavior_schema(defaults),
            description_placeholders={"cover": self._current_cover_label()},
            errors=errors,
        )


# ── Main Config Flow ───────────────────────────────────────────────────────────

class CoverExtenderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Extender."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_TYPE_GLOBAL:   GlobalFlowHandler,
            SUBENTRY_TYPE_FACADE:   FacadeFlowHandler,
            SUBENTRY_TYPE_MODE:     ModeFlowHandler,
            SUBENTRY_TYPE_TEMPLATE: TemplateFlowHandler,
            SUBENTRY_TYPE_COVER:    CoverFlowHandler,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        # Single instance is enforced by "single_config_entry" in manifest.json
        return self.async_create_entry(title="Cover Extender", data={})
