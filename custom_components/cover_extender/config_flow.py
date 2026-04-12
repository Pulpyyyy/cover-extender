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
from homeassistant.helpers import selector, translation as ha_translation
from homeassistant.core import HomeAssistant, callback

from .const import (
    DEFAULT_COMMAND_INTERVAL_MS,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_MODE,
    SUBENTRY_TYPE_TEMPLATE,
)

_WEATHER_CONDITIONS = [
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
]

_ACTION_ADD = "__add__"

_TITLE_FALLBACKS: dict[str, str] = {
    "facade":         "Facades",
    "mode":           "Modes",
    "cover_template": "Templates",
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

_DEFAULT_COLOR_HEX = "#2196F3"
_DEFAULT_COLOR_RGB = [33, 150, 243]


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
    """Return existing subentry data for individual-subentry reconfigure flows."""
    try:
        subentry_id = (
            getattr(flow, "_subentry_id", None)
            or getattr(flow, "subentry_id", None)
            or flow.context.get("subentry_id")
        )
        if subentry_id:
            sub = flow.config_entry.subentries.get(subentry_id)
            if sub:
                return dict(sub.data)
    except AttributeError:
        pass
    return {}


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
            existing_entry, existing, data={"items": items}
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


# ── Facade Flow (singleton) ────────────────────────────────────────────────────

class FacadeFlowHandler(ConfigSubentryFlow):
    """Manage facades as a singleton subentry containing an items list."""

    _items: list[dict[str, Any]]
    _edit_idx: int

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
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add facade"}]
        for i, item in enumerate(self._items):
            options.append({"value": f"select:{i}", "label": item["name"]})

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="facade_manage")
                )
            }),
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
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [facade] delete: removed '%s', %d item(s) remaining", removed.get("name"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_FACADE, self._items)
        return await self.async_step_manage()

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            _LOGGER.debug("config_flow [facade] async_step_add: adding '%s'", user_input.get("name"))
            self._items.append(user_input)
            _LOGGER.debug("config_flow [facade] async_step_add: saving %d item(s)", len(self._items))
            return _singleton_save(self, SUBENTRY_TYPE_FACADE, await _subentry_title(self.hass, SUBENTRY_TYPE_FACADE), self._items)
        return self.async_show_form(step_id="add", data_schema=self._item_schema())

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            _LOGGER.debug("config_flow [facade] async_step_edit: updating index %d → '%s'", self._edit_idx, user_input.get("name"))
            self._items[self._edit_idx] = user_input
            return _singleton_save(self, SUBENTRY_TYPE_FACADE, await _subentry_title(self.hass, SUBENTRY_TYPE_FACADE), self._items)
        return self.async_show_form(
            step_id="edit",
            data_schema=self.add_suggested_values_to_schema(
                self._item_schema(), self._items[self._edit_idx]
            ),
        )


# ── Mode Flow (singleton) ──────────────────────────────────────────────────────

class ModeFlowHandler(ConfigSubentryFlow):
    """Manage modes as a singleton subentry containing an items list."""

    _items: list[dict[str, Any]]
    _edit_idx: int

    @staticmethod
    def _item_schema() -> vol.Schema:
        return vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Optional("icon",     default="mdi:label"):  selector.IconSelector(),
            vol.Optional("color",    default=_DEFAULT_COLOR_RGB): selector.ColorRGBSelector(),
            vol.Optional("lock",     default=False):         selector.BooleanSelector(),
            vol.Optional("behavior"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["auto", "manual", "ignore"],
                    mode="dropdown",
                    translation_key="mode_behavior",
                )
            ),
            vol.Optional("hidden", default=False): selector.BooleanSelector(),
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
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add mode"}]
        for i, item in enumerate(self._items):
            options.append({"value": f"select:{i}", "label": item["name"]})

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="mode_manage")
                )
            }),
        )

    async def async_step_item(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        item_name = self._items[self._edit_idx]["name"]
        _LOGGER.debug("config_flow [mode] async_step_item: showing menu for '%s'", item_name)
        return self.async_show_menu(
            step_id="item",
            menu_options=["edit", "delete"],
            description_placeholders={"name": item_name},
        )

    async def async_step_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [mode] delete: removed '%s', %d item(s) remaining", removed.get("name"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_MODE, self._items)
        return await self.async_step_manage()

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
        if user_input is not None:
            _LOGGER.debug("config_flow [mode] async_step_add: adding '%s'", user_input.get("name"))
            self._items.append(self._ui_to_item(user_input))
            return _singleton_save(self, SUBENTRY_TYPE_MODE, await _subentry_title(self.hass, SUBENTRY_TYPE_MODE), self._items)
        return self.async_show_form(step_id="add", data_schema=self._item_schema())

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            _LOGGER.debug("config_flow [mode] async_step_edit: updating index %d → '%s'", self._edit_idx, user_input.get("name"))
            self._items[self._edit_idx] = self._ui_to_item(user_input)
            return _singleton_save(self, SUBENTRY_TYPE_MODE, await _subentry_title(self.hass, SUBENTRY_TYPE_MODE), self._items)
        return self.async_show_form(
            step_id="edit",
            data_schema=self.add_suggested_values_to_schema(
                self._item_schema(), self._item_to_ui(self._items[self._edit_idx])
            ),
        )


# ── Template Flow (singleton, two-step wizard per item) ────────────────────────

class TemplateFlowHandler(ConfigSubentryFlow):
    """Manage cover templates as a singleton subentry containing an items list."""

    _items: list[dict[str, Any]]
    _edit_idx: int
    _pending_identity: dict[str, Any]

    @staticmethod
    def _identity_schema() -> vol.Schema:
        return vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("angle_left",  default=90): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=90, mode="slider", unit_of_measurement="°")
            ),
            vol.Required("angle_right", default=90): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=90, mode="slider", unit_of_measurement="°")
            ),
        })

    @staticmethod
    def _automation_schema() -> vol.Schema:
        return vol.Schema({
            vol.Optional("shade_enable",           default=True):  selector.BooleanSelector(),
            vol.Optional("shade_distance",         default=1.0):   selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=50,  step=0.1, mode="box", unit_of_measurement="m")
            ),
            vol.Optional("shade_max_height",       default=2.0):   selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=10,  step=0.05, mode="box", unit_of_measurement="m")
            ),
            vol.Optional("shade_degrees",          default=90):    selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=180, mode="slider", unit_of_measurement="°")
            ),
            vol.Optional("shade_minimum_position", default=0):     selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, mode="slider", unit_of_measurement="%")
            ),
            vol.Optional("shade_time_out",         default=2):     selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=60,  mode="box", unit_of_measurement="min")
            ),
            vol.Optional("solar_gain_enable",         default=False): selector.BooleanSelector(),
            vol.Optional("solar_gain_position_solar", default=100):   selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, mode="slider", unit_of_measurement="%")
            ),
        })

    @staticmethod
    def _pack_automation(ui: dict[str, Any]) -> dict[str, Any]:
        return {
            "shade": {
                "enable":           ui.get("shade_enable",           True),
                "distance":         ui.get("shade_distance",         1.0),
                "max_height":       ui.get("shade_max_height",       2.0),
                "degrees":          ui.get("shade_degrees",          90),
                "minimum_position": ui.get("shade_minimum_position", 0),
                "time_out":         ui.get("shade_time_out",         2),
            },
            "solar_gain": {
                "enable":         ui.get("solar_gain_enable",         False),
                "position_solar": ui.get("solar_gain_position_solar", 100),
            },
        }

    @staticmethod
    def _flatten_automation(d: dict[str, Any]) -> dict[str, Any]:
        shade = d.get("shade", {})
        sg    = d.get("solar_gain", {})
        return {
            "shade_enable":              shade.get("enable",           True),
            "shade_distance":            shade.get("distance",         1.0),
            "shade_max_height":          shade.get("max_height",       2.0),
            "shade_degrees":             shade.get("degrees",          90),
            "shade_minimum_position":    shade.get("minimum_position", 0),
            "shade_time_out":            shade.get("time_out",         2),
            "solar_gain_enable":         sg.get("enable",              False),
            "solar_gain_position_solar": sg.get("position_solar",      100),
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
        options: list[dict[str, str]] = [{"value": _ACTION_ADD, "label": "Add template"}]
        for i, item in enumerate(self._items):
            options.append({"value": f"select:{i}", "label": item["name"]})

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode="list", translation_key="template_manage")
                )
            }),
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
        removed = self._items.pop(self._edit_idx)
        _LOGGER.debug("config_flow [template] delete: removed '%s', %d item(s) remaining", removed.get("name"), len(self._items))
        _update_singleton_in_place(self, SUBENTRY_TYPE_TEMPLATE, self._items)
        return await self.async_step_manage()

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            _LOGGER.debug("config_flow [template] async_step_add: identity '%s'", user_input.get("name"))
            self._pending_identity = user_input
            return await self.async_step_add_automation()
        return self.async_show_form(step_id="add", data_schema=self._identity_schema())

    async def async_step_add_automation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._items.append({**self._pending_identity, **self._pack_automation(user_input)})
            _LOGGER.debug("config_flow [template] async_step_add_automation: saving %d item(s)", len(self._items))
            return _singleton_save(self, SUBENTRY_TYPE_TEMPLATE, await _subentry_title(self.hass, SUBENTRY_TYPE_TEMPLATE), self._items)
        return self.async_show_form(step_id="add_automation", data_schema=self._automation_schema())

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing = self._items[self._edit_idx]
        if user_input is not None:
            _LOGGER.debug("config_flow [template] async_step_edit: identity '%s' at index %d", user_input.get("name"), self._edit_idx)
            self._pending_identity = user_input
            return await self.async_step_edit_automation()
        identity = {k: existing[k] for k in ("name", "angle_left", "angle_right") if k in existing}
        return self.async_show_form(
            step_id="edit",
            data_schema=self.add_suggested_values_to_schema(self._identity_schema(), identity),
        )

    async def async_step_edit_automation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        existing = self._items[self._edit_idx]
        if user_input is not None:
            self._items[self._edit_idx] = {**self._pending_identity, **self._pack_automation(user_input)}
            _LOGGER.debug("config_flow [template] async_step_edit_automation: saving %d item(s)", len(self._items))
            return _singleton_save(self, SUBENTRY_TYPE_TEMPLATE, await _subentry_title(self.hass, SUBENTRY_TYPE_TEMPLATE), self._items)
        return self.async_show_form(
            step_id="edit_automation",
            data_schema=self.add_suggested_values_to_schema(
                self._automation_schema(), self._flatten_automation(existing)
            ),
        )


# ── Cover Flow (individual subentry) ──────────────────────────────────────────

class CoverFlowHandler(ConfigSubentryFlow):
    """Create or edit a cover profile subentry."""

    def _schema(self) -> vol.Schema:
        facades   = _names_from_hass(self.hass, SUBENTRY_TYPE_FACADE)
        templates = _names_from_hass(self.hass, SUBENTRY_TYPE_TEMPLATE)
        return vol.Schema({
            vol.Required("entity_id"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="cover")
            ),
            vol.Optional("entity_picture"): selector.TextSelector(),
            vol.Required("facade"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=facades or [""], mode="dropdown")
            ),
            vol.Optional("template"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=templates or [""], mode="dropdown")
            ),
            vol.Optional("exclusion"): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
        })

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            _LOGGER.debug("config_flow [cover] async_step_user: adding cover '%s'", user_input.get("entity_id"))
            return self.async_create_entry(
                title=user_input.get("entity_id", "cover"), data=user_input
            )
        return self.async_show_form(step_id="user", data_schema=self._schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            _LOGGER.debug("config_flow [cover] async_step_reconfigure: updating cover '%s'", user_input.get("entity_id"))
            return self.async_create_entry(
                title=user_input.get("entity_id", "cover"), data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(), _reconfigure_data(self)
            ),
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
            SUBENTRY_TYPE_FACADE:   FacadeFlowHandler,
            SUBENTRY_TYPE_MODE:     ModeFlowHandler,
            SUBENTRY_TYPE_TEMPLATE: TemplateFlowHandler,
            SUBENTRY_TYPE_COVER:    CoverFlowHandler,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            return self.async_create_entry(
                title="Cover Extender", data={}, options=user_input
            )
        return self.async_show_form(
            step_id="user", data_schema=self._build_global_schema()
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return self.async_create_entry(
            title="Cover Extender", data=import_data, options={}
        )

    @staticmethod
    def _build_global_schema() -> vol.Schema:
        return vol.Schema({
            vol.Required(
                "command_interval", default=DEFAULT_COMMAND_INTERVAL_MS
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=5000, step=100, mode="box", unit_of_measurement="ms"
                )
            ),
            vol.Optional("show_sun_facing", default=True):  selector.BooleanSelector(),
            vol.Optional("show_auto_shade", default=True):  selector.BooleanSelector(),
            vol.Optional("show_solar_gain", default=False): selector.BooleanSelector(),
            vol.Optional("sg_temperature_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional("sg_temperature_threshold", default="20"): selector.TextSelector(),
            vol.Optional("sg_weather_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(
                "sg_good_conditions", default=["sunny", "partlycloudy"]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_WEATHER_CONDITIONS, multiple=True, mode="dropdown"
                )
            ),
        })

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CoverExtenderOptionsFlow:
        return CoverExtenderOptionsFlow()


# ── Options Flow ───────────────────────────────────────────────────────────────

class CoverExtenderOptionsFlow(config_entries.OptionsFlow):
    """Reconfigure global settings for Cover Extender."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                CoverExtenderConfigFlow._build_global_schema(),
                self.config_entry.options,
            ),
        )
