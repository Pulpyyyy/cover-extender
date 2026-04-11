"""Config flow for Cover Extender.

UI mode: all configuration is done via subentries (facades, modes, covers).

Subentry types
  global   — one instance, global settings (command_interval, show_entities, solar_gain)
  facade   — N instances, one per facade (name + azimuth)
  mode     — N instances, one per global mode definition
  cover    — N instances, one per cover profile (3-step wizard)
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DEFAULT_COMMAND_INTERVAL_MS,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_GLOBAL,
    SUBENTRY_TYPE_MODE,
    SUBENTRY_TYPE_TEMPLATE,
)
from .schemas import SHADE_DEFAULTS

# Common weather condition values offered in the global solar-gain selector
_WEATHER_CONDITIONS = [
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
]


# ── Small helpers ─────────────────────────────────────────────────────────────

def _parse_threshold(raw: Any) -> float | str:
    """Convert threshold input to float if numeric, keep as entity_id string otherwise."""
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError):
        return str(raw).strip()


# ── Selector helpers ──────────────────────────────────────────────────────────

def _number_box(
    min_val: float,
    max_val: float,
    step: float = 1.0,
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_val,
            max=max_val,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _slider(
    min_val: float = 0,
    max_val: float = 100,
    step: float = 1.0,
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_val,
            max=max_val,
            step=step,
            mode=selector.NumberSelectorMode.SLIDER,
        )
    )


# ── Main config flow ──────────────────────────────────────────────────────────

class CoverExtenderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cover Extender."""

    VERSION = 1

    @classmethod
    def async_get_supported_subentry_types(
        cls,
        config_entry: config_entries.ConfigEntry,
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        return {
            SUBENTRY_TYPE_FACADE:   FacadeSubentryFlow,
            SUBENTRY_TYPE_MODE:     ModeSubentryFlow,
            SUBENTRY_TYPE_COVER:    CoverSubentryFlow,
            SUBENTRY_TYPE_GLOBAL:   GlobalSubentryFlow,
            SUBENTRY_TYPE_TEMPLATE: CoverTemplateSubentryFlow,
        }

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create the single Cover Extender entry in UI mode."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Cover Extender", data={})


# ── Subentry flow base (HA 2025.x compat) ────────────────────────────────────

class _CoverExtenderSubentryFlowBase(config_entries.ConfigSubentryFlow):
    """Base for all Cover Extender subentry flows.

    In HA 2025.x, ConfigSubentryFlow is instantiated via
    ``subentry_types[subentry_type]()`` (no constructor arguments) and
    ``config_entry`` is no longer automatically set as an instance attribute.
    We resolve it on demand through ``hass`` + ``context["entry_id"]``.
    Using ``__getattr__`` means we only intercept the lookup when HA has *not*
    set the attribute directly (forward-compatible with older HA releases).
    """

    def __getattr__(self, name: str):  # noqa: ANN204
        if name == "config_entry":
            # Try context key (varies across HA versions)
            for key in ("entry_id", "config_entry_id", "parent_entry_id"):
                entry_id: str | None = self.context.get(key)
                if entry_id:
                    entry = self.hass.config_entries.async_get_entry(entry_id)
                    if entry is not None:
                        return entry
            # Fallback: Cover Extender enforces a singleton entry — find it by domain
            entries = self.hass.config_entries.async_entries(DOMAIN)
            if entries:
                return entries[0]
            raise AttributeError("No Cover Extender config entry found")
        if name == "_subentry":
            subentry_id: str | None = self.context.get("subentry_id")
            if not subentry_id:
                return None
            return self.config_entry.subentries.get(subentry_id)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )


# ── Facade subentry flow ──────────────────────────────────────────────────────

class FacadeSubentryFlow(_CoverExtenderSubentryFlowBase):
    """Add or edit a facade definition."""

    def _existing_names(self, exclude_id: str | None = None) -> set[str]:
        return {
            sub.data["name"]
            for sub in self.config_entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_FACADE
            and sub.subentry_id != exclude_id
        }

    def _build_schema(self, defaults: dict | None = None) -> vol.Schema:
        d = defaults or {}
        return vol.Schema({
            vol.Required("name", default=d.get("name", "")): selector.TextSelector(),
            vol.Required("azimuth", default=d.get("azimuth", 180.0)): _number_box(0, 360, 0.1),
        })

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "name_required"
            elif name in self._existing_names():
                errors["name"] = "facade_name_exists"
            else:
                data = {"name": name, "azimuth": float(user_input["azimuth"])}
                return self.async_create_entry(title=name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        subentry = self._subentry
        if user_input is not None:
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "name_required"
            elif name in self._existing_names(exclude_id=subentry.subentry_id):
                errors["name"] = "facade_name_exists"
            else:
                data = {"name": name, "azimuth": float(user_input["azimuth"])}
                return self.async_update_and_abort(
                    self.config_entry, subentry,
                    title=name, data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_schema(subentry.data if subentry else {}),
            errors=errors,
        )


# ── Mode subentry flow ────────────────────────────────────────────────────────

class ModeSubentryFlow(_CoverExtenderSubentryFlowBase):
    """Add, edit, or delete a global mode definition."""

    def _existing_names(self, exclude_id: str | None = None) -> set[str]:
        return {
            sub.data["name"]
            for sub in self.config_entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_MODE
            and sub.subentry_id != exclude_id
        }

    def _build_schema(
        self,
        defaults: dict | None = None,
        include_delete: bool = False,
    ) -> vol.Schema:
        d = defaults or {}
        schema: dict[Any, Any] = {
            vol.Required("name", default=d.get("name", "")): selector.TextSelector(),
            vol.Optional("icon",    default=d.get("icon",    "mdi:help-circle")): selector.TextSelector(),
            vol.Optional("color",   default=d.get("color",   "#FFFFFF")): selector.TextSelector(),
            vol.Optional("lock",    default=d.get("lock",    False)): selector.BooleanSelector(),
            vol.Optional("behavior", default=d.get("behavior") or ""): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="",           label="None"),
                        selector.SelectOptionDict(value="auto_shade", label="Auto shade"),
                        selector.SelectOptionDict(value="solar_gain", label="Solar gain"),
                    ]
                )
            ),
            vol.Optional("advanced_section"): selector.SectionSelector(
                selector.SectionSelectorConfig(collapsed=True)
            ),
            vol.Optional("hidden",  default=d.get("hidden",  False)): selector.BooleanSelector(),
        }
        if include_delete:
            schema[vol.Optional("delete_mode", default=False)] = selector.BooleanSelector()
        return vol.Schema(schema)

    def _parse(self, user_input: dict) -> dict:
        return {
            "name":     user_input["name"].strip(),
            "icon":     user_input.get("icon",     "mdi:help-circle"),
            "color":    user_input.get("color",    "#FFFFFF"),
            "lock":     bool(user_input.get("lock",    False)),
            "behavior": user_input.get("behavior") or None,
            "hidden":   bool(user_input.get("hidden",  False)),
        }

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "name_required"
            elif name in self._existing_names():
                errors["name"] = "mode_name_exists"
            else:
                return self.async_create_entry(title=name, data=self._parse(user_input))

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        subentry = self._subentry
        if user_input is not None:
            if user_input.get("delete_mode"):
                return await self.async_step_confirm_delete()
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "name_required"
            elif name in self._existing_names(exclude_id=subentry.subentry_id):
                errors["name"] = "mode_name_exists"
            else:
                return self.async_update_and_abort(
                    self.config_entry, subentry,
                    title=name, data=self._parse(user_input),
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_schema(
                subentry.data if subentry else {}, include_delete=True
            ),
            errors=errors,
        )

    async def async_step_confirm_delete(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show cascade impact and ask for confirmation before deleting a mode."""
        subentry = self._subentry
        mode_name = subentry.data["name"]

        # Find covers that reference this mode
        impacted: list[str] = [
            sub.data.get("entity_id", sub.subentry_id)
            for sub in self.config_entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_COVER
            and mode_name in sub.data.get("modes", {})
        ]

        if user_input is not None:
            # Cascade: strip the mode from every impacted cover subentry
            for sub in list(self.config_entry.subentries.values()):
                if (
                    sub.subentry_type == SUBENTRY_TYPE_COVER
                    and mode_name in sub.data.get("modes", {})
                ):
                    new_modes = {
                        k: v
                        for k, v in sub.data["modes"].items()
                        if k != mode_name
                    }
                    self.hass.config_entries.async_update_subentry(
                        self.config_entry, sub,
                        data={**sub.data, "modes": new_modes},
                    )
            # Remove the mode subentry itself
            self.hass.config_entries.async_remove_subentry(
                self.config_entry, subentry.subentry_id
            )
            return self.async_abort(reason="mode_deleted")

        return self.async_show_form(
            step_id="confirm_delete",
            data_schema=vol.Schema({}),
            description_placeholders={
                "mode":   mode_name,
                "covers": ", ".join(impacted) if impacted else "—",
                "count":  str(len(impacted)),
            },
            errors={},
        )


# ── Cover subentry flow (3 steps) ─────────────────────────────────────────────

class CoverSubentryFlow(_CoverExtenderSubentryFlowBase):
    """Multi-step wizard to create or edit a cover profile.

    Step flow (creation):
        user  →  cover_modes_select  →  cover_modes_config  →  cover_automation

    Step flow (reconfigure):
        reconfigure  →  cover_modes_select  →  cover_modes_config  →  cover_automation
    """

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _facade_options(self) -> list[selector.SelectOptionDict]:
        return [
            selector.SelectOptionDict(value=s.data["name"], label=s.data["name"])
            for s in self.config_entry.subentries.values()
            if s.subentry_type == SUBENTRY_TYPE_FACADE
        ]

    def _mode_options(self) -> list[str]:
        return [
            s.data["name"]
            for s in self.config_entry.subentries.values()
            if s.subentry_type == SUBENTRY_TYPE_MODE
        ]

    def _template_options(self) -> list[selector.SelectOptionDict]:
        return [
            selector.SelectOptionDict(value=s.data["name"], label=s.data["name"])
            for s in self.config_entry.subentries.values()
            if s.subentry_type == SUBENTRY_TYPE_TEMPLATE
        ]

    # ── Step 1 — cover identity ───────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        self._is_reconfigure = False
        self._cover_data: dict[str, Any] = {}
        self._selected_modes: list[str] = []
        self._use_template: bool = False
        return await self._identity_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        self._is_reconfigure = True
        # Initialize lazily (only on first call — subsequent calls must keep state)
        if not hasattr(self, "_cover_data"):
            self._cover_data = {}
        if not hasattr(self, "_selected_modes"):
            self._selected_modes = []
        if not hasattr(self, "_use_template"):
            self._use_template = False
        # Pre-populate on first call
        if user_input is None and self._subentry and not self._cover_data:
            self._cover_data = dict(self._subentry.data)
            self._use_template = bool(self._cover_data.get("template", ""))
        return await self._identity_step("reconfigure", user_input)

    async def _identity_step(
        self,
        step_id: str,
        user_input: dict | None,
    ) -> config_entries.ConfigFlowResult:
        """Step 1: entity identity, facade, optional template, exclusion."""
        errors: dict[str, str] = {}
        facade_opts = self._facade_options()
        template_opts = self._template_options()

        if user_input is not None:
            entity_id = (user_input.get("entity_id") or "").strip()
            if not entity_id:
                errors["entity_id"] = "entity_required"
            else:
                selected_template = (user_input.get("template") or "").strip()
                self._use_template = bool(selected_template)
                self._cover_data.update({
                    "entity_id":      entity_id,
                    "entity_picture": user_input.get("entity_picture", ""),
                    "facade":         user_input.get("facade", ""),
                    "exclusion":      list(user_input.get("exclusion") or []),
                })
                if self._use_template:
                    self._cover_data["template"] = selected_template
                    # Drop manual fields if switching from manual to template
                    for key in ("angle_left", "angle_right", "shade", "solar_gain"):
                        self._cover_data.pop(key, None)
                    return await self.async_step_cover_modes_select()
                else:
                    self._cover_data.pop("template", None)
                    return await self.async_step_cover_angles()

        cur = self._cover_data
        schema_fields: dict[Any, Any] = {
            vol.Required("entity_id", default=cur.get("entity_id", "")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="cover")
            ),
            vol.Optional("entity_picture", default=cur.get("entity_picture", "")): selector.TextSelector(),
        }
        # ── Facade / template section (only shown when at least one option exists) ──
        if facade_opts or template_opts:
            schema_fields[vol.Optional("facade_section")] = selector.SectionSelector(
                selector.SectionSelectorConfig(collapsed=True)
            )
            if facade_opts:
                schema_fields[vol.Optional("facade", default=cur.get("facade", ""))] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(options=facade_opts)
                    )
                )
            if template_opts:
                schema_fields[vol.Optional("template", default=cur.get("template", ""))] = (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[selector.SelectOptionDict(value="", label="— None —")] + template_opts,
                        )
                    )
                )
        # ── Exclusion section ─────────────────────────────────────────────────────
        schema_fields[vol.Optional("exclusion_section")] = selector.SectionSelector(
            selector.SectionSelectorConfig(collapsed=True)
        )
        schema_fields[vol.Optional("exclusion", default=list(cur.get("exclusion") or []))] = (
            selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))
        )

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    # ── Step 1b — angles (only when no template) ─────────────────────────────

    async def async_step_cover_angles(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect angle_left / angle_right for covers that don't use a template."""
        if user_input is not None:
            self._cover_data.update({
                "angle_left":  float(user_input.get("angle_left",  85.0)),
                "angle_right": float(user_input.get("angle_right", 85.0)),
            })
            return await self.async_step_cover_modes_select()

        cur = self._cover_data
        return self.async_show_form(
            step_id="cover_angles",
            data_schema=vol.Schema({
                vol.Optional("angle_left",  default=float(cur.get("angle_left",  85.0))): _number_box(0, 90, 0.5),
                vol.Optional("angle_right", default=float(cur.get("angle_right", 85.0))): _number_box(0, 90, 0.5),
            }),
            errors={},
        )

    # ── Step 2a — select which modes to configure ─────────────────────────────

    async def async_step_cover_modes_select(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._selected_modes = list(user_input.get("modes", []))
            if self._selected_modes:
                return await self.async_step_cover_modes_config()
            self._cover_data["modes"] = {}
            return await self.async_step_cover_automation()

        available = self._mode_options()
        # Pre-select modes already present in this cover's config
        existing_selected = [
            m for m in self._cover_data.get("modes", {}) if m in available
        ]

        return self.async_show_form(
            step_id="cover_modes_select",
            data_schema=vol.Schema({
                vol.Optional("modes_section"): selector.SectionSelector(
                    selector.SectionSelectorConfig(collapsed=False)
                ),
                vol.Optional("modes", default=existing_selected): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=m, label=m)
                            for m in available
                        ],
                        multiple=True,
                    )
                ),
            }),
            errors={},
        )

    # ── Step 2b — configure type + value for each selected mode ───────────────

    async def async_step_cover_modes_config(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            modes: dict[str, Any] = {}
            for mode_name in self._selected_modes:
                # field names use double-underscore to avoid collision with mode names
                mode_type  = user_input.get(f"{mode_name}__type", "fixed")
                mode_value = user_input.get(f"{mode_name}__value", "")
                if mode_type == "fixed":
                    try:
                        val: Any = int(float(mode_value))
                    except (ValueError, TypeError):
                        val = None
                    modes[mode_name] = {"type": "fixed", "value": val}
                elif mode_type == "entity":
                    cleaned = str(mode_value).strip() if mode_value else None
                    modes[mode_name] = {"type": "entity", "value": cleaned}
                else:  # "auto"
                    modes[mode_name] = {"type": "auto", "value": None}
            self._cover_data["modes"] = modes
            if self._use_template:
                return self._finish_flow()
            return await self.async_step_cover_automation()

        # Build a dynamic schema with one type-selector + one value-field per mode
        existing_modes: dict = self._cover_data.get("modes", {})
        schema_dict: dict[Any, Any] = {}
        for mode_name in self._selected_modes:
            existing = existing_modes.get(mode_name) or {}
            ex_type  = existing.get("type", "fixed") if isinstance(existing, dict) else "fixed"
            ex_value = existing.get("value", "")     if isinstance(existing, dict) else ""
            schema_dict[vol.Optional(f"{mode_name}__type", default=ex_type)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="fixed",  label="Fixed"),
                            selector.SelectOptionDict(value="auto",   label="Auto"),
                            selector.SelectOptionDict(value="entity", label="Entity"),
                        ]
                    )
                )
            )
            schema_dict[vol.Optional(f"{mode_name}__value", default=str(ex_value) if ex_value is not None else "")] = (
                selector.TextSelector()
            )

        return self.async_show_form(
            step_id="cover_modes_config",
            data_schema=vol.Schema(schema_dict),
            errors={},
        )

    # ── Step 3 — automation (shade + solar_gain + exclusion) ─────────────────

    async def async_step_cover_automation(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        _sd = SHADE_DEFAULTS
        if user_input is not None:
            self._cover_data["shade"] = {
                "enable":           bool(user_input.get("shade_enable",           _sd["enable"])),
                "distance":         float(user_input.get("shade_distance",         _sd["distance"])),
                "max_height":       float(user_input.get("shade_max_height",       _sd["max_height"])),
                "min_height":       float(user_input.get("shade_min_height",       _sd["min_height"])),
                "degrees":          float(user_input.get("shade_degrees",          _sd["degrees"])),
                "max_elevation":    float(user_input.get("shade_max_elevation",    _sd["max_elevation"])),
                "min_elevation":    float(user_input.get("shade_min_elevation",    _sd["min_elevation"])),
                "minimum_position": float(user_input.get("shade_minimum_position", _sd["minimum_position"])),
                "default_position": float(user_input.get("shade_default_position", _sd["default_position"])),
                "change_threshold": float(user_input.get("shade_change_threshold", _sd["change_threshold"])),
                "time_out":         float(user_input.get("shade_time_out",         _sd["time_out"])),
            }
            self._cover_data["solar_gain"] = {
                "enable":         bool(user_input.get("solar_gain_enable",         False)),
                "position_cold":  int(user_input.get("solar_gain_position_cold",   0)),
                "position_solar": int(user_input.get("solar_gain_position_solar",  100)),
            }
            return self._finish_flow()

        cur_shade = self._cover_data.get("shade") or {}
        cur_sg    = self._cover_data.get("solar_gain") or {}

        schema = vol.Schema({
            # ── Shade section ─────────────────────────────────────────────────
            vol.Optional("shade"): selector.SectionSelector(
                selector.SectionSelectorConfig(collapsed=False)
            ),
            vol.Optional("shade_enable",           default=bool(cur_shade.get("enable",           _sd["enable"]))): selector.BooleanSelector(),
            vol.Optional("shade_distance",         default=float(cur_shade.get("distance",         _sd["distance"]))): _number_box(0, 10, 0.1),
            vol.Optional("shade_max_height",       default=float(cur_shade.get("max_height",       _sd["max_height"]))): _number_box(0, 10, 0.1),
            vol.Optional("shade_min_height",       default=float(cur_shade.get("min_height",       _sd["min_height"]))): _number_box(0, 10, 0.1),
            vol.Optional("shade_degrees",          default=float(cur_shade.get("degrees",          _sd["degrees"]))): _number_box(0, 360, 1),
            vol.Optional("shade_max_elevation",    default=float(cur_shade.get("max_elevation",    _sd["max_elevation"]))): _number_box(0, 90, 1),
            vol.Optional("shade_min_elevation",    default=float(cur_shade.get("min_elevation",    _sd["min_elevation"]))): _number_box(0, 90, 1),
            vol.Optional("shade_minimum_position", default=float(cur_shade.get("minimum_position", _sd["minimum_position"]))): _slider(0, 100),
            vol.Optional("shade_default_position", default=float(cur_shade.get("default_position", _sd["default_position"]))): _slider(0, 100),
            vol.Optional("shade_change_threshold", default=float(cur_shade.get("change_threshold", _sd["change_threshold"]))): _number_box(0, 50, 1),
            vol.Optional("shade_time_out",         default=float(cur_shade.get("time_out",         _sd["time_out"]))): _number_box(0, 60, 0.5),
            # ── Solar gain section ────────────────────────────────────────────
            vol.Optional("solar_gain"): selector.SectionSelector(
                selector.SectionSelectorConfig(collapsed=False)
            ),
            vol.Optional("solar_gain_enable",         default=bool(cur_sg.get("enable",         False))): selector.BooleanSelector(),
            vol.Optional("solar_gain_position_cold",  default=int(cur_sg.get("position_cold",   0))): _slider(0, 100),
            vol.Optional("solar_gain_position_solar", default=int(cur_sg.get("position_solar",  100))): _slider(0, 100),
        })

        return self.async_show_form(
            step_id="cover_automation",
            data_schema=schema,
            errors={},
        )

    # ── Finish (create or update) ─────────────────────────────────────────────

    def _finish_flow(self) -> config_entries.ConfigFlowResult:
        entity_id = self._cover_data["entity_id"]
        if self._is_reconfigure and self._subentry:
            return self.async_update_and_abort(
                self.config_entry,
                self._subentry,
                title=entity_id,
                data=self._cover_data,
            )
        return self.async_create_entry(title=entity_id, data=self._cover_data)


# ── Global subentry flow ──────────────────────────────────────────────────────

class GlobalSubentryFlow(_CoverExtenderSubentryFlowBase):
    """Single-instance subentry for global Cover Extender settings."""

    def _build_schema(self, defaults: dict | None = None) -> vol.Schema:
        d   = defaults or {}
        sg  = d.get("solar_gain",    {})
        se  = d.get("show_entities", {})
        return vol.Schema({
            vol.Optional("command_interval",    default=int(d.get("command_interval", DEFAULT_COMMAND_INTERVAL_MS))): _number_box(0, 5000, 10),
            # show_entities
            vol.Optional("show_sun_facing",     default=bool(se.get("sun_facing", False))): selector.BooleanSelector(),
            vol.Optional("show_auto_shade",     default=bool(se.get("auto_shade", False))): selector.BooleanSelector(),
            vol.Optional("show_solar_gain",     default=bool(se.get("solar_gain", False))): selector.BooleanSelector(),
            # solar_gain global
            vol.Optional("sg_temperature_entity",    default=sg.get("temperature_entity") or ""): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
            vol.Optional("sg_temperature_threshold", default=str(sg.get("temperature_threshold", "19.0"))): selector.TextSelector(),
            vol.Optional("sg_weather_entity",        default=sg.get("weather_entity") or ""): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional("sg_good_conditions",       default=list(sg.get("good_conditions") or [])): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_WEATHER_CONDITIONS,
                    multiple=True,
                    custom_value=True,
                )
            ),
        })

    def _parse(self, user_input: dict) -> dict:
        return {
            "command_interval": int(user_input.get("command_interval", DEFAULT_COMMAND_INTERVAL_MS)),
            "show_entities": {
                "sun_facing": bool(user_input.get("show_sun_facing", False)),
                "auto_shade": bool(user_input.get("show_auto_shade", False)),
                "solar_gain": bool(user_input.get("show_solar_gain", False)),
            },
            "solar_gain": {
                "temperature_entity":    user_input.get("sg_temperature_entity") or None,
                "temperature_threshold": _parse_threshold(user_input.get("sg_temperature_threshold", "19.0")),
                "weather_entity":        user_input.get("sg_weather_entity") or None,
                "good_conditions":       list(user_input.get("sg_good_conditions") or []),
            },
        }

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        # Enforce singleton
        existing = [
            s for s in self.config_entry.subentries.values()
            if s.subentry_type == SUBENTRY_TYPE_GLOBAL
        ]
        if existing:
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(
                title="Global settings", data=self._parse(user_input)
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(),
            errors={},
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        subentry = self._subentry
        if user_input is not None:
            return self.async_update_and_abort(
                self.config_entry, subentry,
                title="Global settings", data=self._parse(user_input),
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_schema(subentry.data if subentry else {}),
            errors={},
        )


# ── Cover template subentry flow ──────────────────────────────────────────────

class CoverTemplateSubentryFlow(_CoverExtenderSubentryFlowBase):
    """Add or edit a cover template (shared angle + shade/solar_gain settings).

    A template groups the physical-window parameters that are identical for
    several covers: angle_left, angle_right, and the full shade/solar_gain
    configuration.  Covers referencing a template inherit these values at
    runtime; the template is the single source of truth.

    Steps
        user / reconfigure  →  template_automation  →  done
    """

    def _existing_names(self, exclude_id: str | None = None) -> set[str]:
        return {
            sub.data["name"]
            for sub in self.config_entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_TEMPLATE
            and sub.subentry_id != exclude_id
        }

    # ── Step 1 — name + angles ────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        self._is_reconfigure = False
        self._template_data: dict[str, Any] = {}
        return await self._identity_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        self._is_reconfigure = True
        if not hasattr(self, "_template_data"):
            self._template_data = {}
        if user_input is None and self._subentry and not self._template_data:
            self._template_data = dict(self._subentry.data)
        return await self._identity_step("reconfigure", user_input)

    async def _identity_step(
        self,
        step_id: str,
        user_input: dict | None,
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            exclude_id = (
                self._subentry.subentry_id
                if self._is_reconfigure and self._subentry
                else None
            )
            if not name:
                errors["name"] = "name_required"
            elif name in self._existing_names(exclude_id=exclude_id):
                errors["name"] = "template_name_exists"
            else:
                self._template_data.update({
                    "name":        name,
                    "angle_left":  float(user_input.get("angle_left",  85.0)),
                    "angle_right": float(user_input.get("angle_right", 85.0)),
                })
                return await self.async_step_template_automation()

        cur = self._template_data
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({
                vol.Required("name",        default=cur.get("name", "")): selector.TextSelector(),
                vol.Optional("angle_left",  default=float(cur.get("angle_left",  85.0))): _number_box(0, 90, 0.5),
                vol.Optional("angle_right", default=float(cur.get("angle_right", 85.0))): _number_box(0, 90, 0.5),
            }),
            errors=errors,
        )

    # ── Step 2 — shade + solar_gain ───────────────────────────────────────────

    async def async_step_template_automation(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        _sd = SHADE_DEFAULTS
        if user_input is not None:
            self._template_data["shade"] = {
                "enable":           bool(user_input.get("shade_enable",           _sd["enable"])),
                "distance":         float(user_input.get("shade_distance",         _sd["distance"])),
                "max_height":       float(user_input.get("shade_max_height",       _sd["max_height"])),
                "min_height":       float(user_input.get("shade_min_height",       _sd["min_height"])),
                "degrees":          float(user_input.get("shade_degrees",          _sd["degrees"])),
                "max_elevation":    float(user_input.get("shade_max_elevation",    _sd["max_elevation"])),
                "min_elevation":    float(user_input.get("shade_min_elevation",    _sd["min_elevation"])),
                "minimum_position": float(user_input.get("shade_minimum_position", _sd["minimum_position"])),
                "default_position": float(user_input.get("shade_default_position", _sd["default_position"])),
                "change_threshold": float(user_input.get("shade_change_threshold", _sd["change_threshold"])),
                "time_out":         float(user_input.get("shade_time_out",         _sd["time_out"])),
            }
            self._template_data["solar_gain"] = {
                "enable":         bool(user_input.get("solar_gain_enable",         False)),
                "position_cold":  int(user_input.get("solar_gain_position_cold",   0)),
                "position_solar": int(user_input.get("solar_gain_position_solar",  100)),
            }
            return self._finish_flow()

        cur_shade = self._template_data.get("shade") or {}
        cur_sg    = self._template_data.get("solar_gain") or {}

        return self.async_show_form(
            step_id="template_automation",
            data_schema=vol.Schema({
                # ── Shade section ─────────────────────────────────────────────
                vol.Optional("shade"): selector.SectionSelector(
                    selector.SectionSelectorConfig(collapsed=False)
                ),
                vol.Optional("shade_enable",           default=bool(cur_shade.get("enable",           _sd["enable"]))): selector.BooleanSelector(),
                vol.Optional("shade_distance",         default=float(cur_shade.get("distance",         _sd["distance"]))): _number_box(0, 10, 0.1),
                vol.Optional("shade_max_height",       default=float(cur_shade.get("max_height",       _sd["max_height"]))): _number_box(0, 10, 0.1),
                vol.Optional("shade_min_height",       default=float(cur_shade.get("min_height",       _sd["min_height"]))): _number_box(0, 10, 0.1),
                vol.Optional("shade_degrees",          default=float(cur_shade.get("degrees",          _sd["degrees"]))): _number_box(0, 360, 1),
                vol.Optional("shade_max_elevation",    default=float(cur_shade.get("max_elevation",    _sd["max_elevation"]))): _number_box(0, 90, 1),
                vol.Optional("shade_min_elevation",    default=float(cur_shade.get("min_elevation",    _sd["min_elevation"]))): _number_box(0, 90, 1),
                vol.Optional("shade_minimum_position", default=float(cur_shade.get("minimum_position", _sd["minimum_position"]))): _slider(0, 100),
                vol.Optional("shade_default_position", default=float(cur_shade.get("default_position", _sd["default_position"]))): _slider(0, 100),
                vol.Optional("shade_change_threshold", default=float(cur_shade.get("change_threshold", _sd["change_threshold"]))): _number_box(0, 50, 1),
                vol.Optional("shade_time_out",         default=float(cur_shade.get("time_out",         _sd["time_out"]))): _number_box(0, 60, 0.5),
                # ── Solar gain section ────────────────────────────────────────
                vol.Optional("solar_gain"): selector.SectionSelector(
                    selector.SectionSelectorConfig(collapsed=False)
                ),
                vol.Optional("solar_gain_enable",         default=bool(cur_sg.get("enable",         False))): selector.BooleanSelector(),
                vol.Optional("solar_gain_position_cold",  default=int(cur_sg.get("position_cold",   0))): _slider(0, 100),
                vol.Optional("solar_gain_position_solar", default=int(cur_sg.get("position_solar",  100))): _slider(0, 100),
            }),
            errors={},
        )

    def _finish_flow(self) -> config_entries.ConfigFlowResult:
        name = self._template_data["name"]
        if self._is_reconfigure and self._subentry:
            return self.async_update_and_abort(
                self.config_entry,
                self._subentry,
                title=name,
                data=self._template_data,
            )
        return self.async_create_entry(title=name, data=self._template_data)
