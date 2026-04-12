"""
Cover Extender — enriches existing cover entities without creating new ones.

Injects custom attributes (entity_picture, facade, modes, auto_shade, sun_facing)
and auto-creates the following helper entities for each configured cover:
  - select.mode_<cover>            mode selector
  - switch.<cover>_lock            automation lock
  - switch.<cover>_auto_shade      autonomous solar shading (shade.enable: true only)
  - switch.<cover>_auto_solar_gain solar gain optimisation (solar_gain.enable: true only)

Mode definition (cover_extender_modes section):
  Each mode can declare an optional `behavior` field — at most one behavior
  can be active at a time (auto_shade and solar_gain are mutually exclusive):
    behavior: auto_shade   → turns on switch.<cover>_auto_shade when mode is applied
    behavior: solar_gain   → turns on switch.<cover>_auto_solar_gain when mode is applied
    behavior: null         → turns off both automation switches (default)

Configuration in configuration.yaml:
  cover_extender:
    source: yaml_entities/covers_config.yaml

Module layout:
  __init__.py     thin entry points (async_setup / async_setup_entry / async_unload_entry)
  coordinator.py  CoverExtenderCoordinator — all business logic
  schemas.py      Voluptuous schemas + YAML loader
  shade.py        Solar geometry helpers (compute_shade_sync, compute_sun_facing …)
  helpers.py      Stateless attribute/position helpers

Available services:
  - cover_extender.apply_mode(mode, entity_id)         apply a mode to one or more covers
  - cover_extender.set_cover_position(entity_id, pos)  move cover(s), respecting the lock
  - cover_extender.open_cover / close_cover             open/close cover(s), respecting lock
  - cover_extender.apply_memory(entity_id)             force-apply stored memory position
  - cover_extender.compute_shade_position(entity_id)   compute solar shade position
  - cover_extender.get_mode_position(entity_id, mode)  return the position set for a mode
  - cover_extender.reload                              reload YAML config without restarting HA
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigSubentry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_SOURCE,
    SERVICE_APPLY_MODE,
    SERVICE_RELOAD,
    SERVICE_GET_MODE_POSITION,
    SERVICE_COMPUTE_SHADE_POSITION,
    SERVICE_SET_COVER_POSITION,
    SERVICE_OPEN_COVER,
    SERVICE_CLOSE_COVER,
    SERVICE_APPLY_MEMORY,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_GLOBAL,
    SUBENTRY_TYPE_MODE,
    SUBENTRY_TYPE_TEMPLATE,
)
from .coordinator import CoverExtenderCoordinator
from .schemas import CONFIG_SCHEMA  # noqa: F401  (re-exported for HA schema discovery)
from .config_flow import _subentry_title

import logging
_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["select", "switch", "binary_sensor"]

_SINGLETON_TYPES = {SUBENTRY_TYPE_FACADE, SUBENTRY_TYPE_MODE, SUBENTRY_TYPE_TEMPLATE, SUBENTRY_TYPE_COVER}
_SINGLETON_TYPES_WITH_GLOBAL = _SINGLETON_TYPES | {SUBENTRY_TYPE_GLOBAL}


async def _async_sync_subentry_titles(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update stored subentry titles to the current HA language.

    HA stores the title set at creation time.  When the UI language changes (or
    when subentries were created in a different language), the stored title drifts
    from the translation.  This re-syncs all singleton subentry titles on startup.
    """
    for sub in entry.subentries.values():
        if sub.subentry_type not in _SINGLETON_TYPES_WITH_GLOBAL:
            continue
        translated = await _subentry_title(hass, sub.subentry_type)
        if sub.title != translated:
            _LOGGER.debug(
                "cover_extender: updating subentry title %r → %r (type=%s)",
                sub.title, translated, sub.subentry_type,
            )
            hass.config_entries.async_update_subentry(entry, sub, title=translated)


def _cleanup_empty_singletons(hass: HomeAssistant) -> None:
    """Remove singleton subentries whose items list is empty.

    These are left behind when a facade/mode/template subentry was created
    then emptied (or created before the singleton-enforcement fix). They
    confuse _find_singleton which would return them before a non-empty one.
    Called synchronously before the coordinator starts so no listener fires.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        for sub in list(entry.subentries.values()):
            if (
                sub.subentry_type in _SINGLETON_TYPES
                and "items" in sub.data
                and not sub.data["items"]
            ):
                _LOGGER.debug(
                    "cover_extender: removing empty singleton subentry %s (type=%s)",
                    sub.subentry_id, sub.subentry_type,
                )
                try:
                    hass.config_entries.async_remove_subentry(entry, sub.subentry_id)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "cover_extender: could not remove empty subentry %s: %s",
                        sub.subentry_id, err,
                    )


async def _async_migrate_yaml_to_subentries(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """One-time migration: convert YAML source config into UI subentries.

    Triggered when entry.data contains CONF_SOURCE (YAML mode) and no subentries
    exist yet.  After migration the source key is cleared from entry.data so the
    migration never runs again.
    """
    from .schemas import load_covers_config

    source = entry.data.get(CONF_SOURCE)
    if not source:
        return
    if entry.subentries:
        _LOGGER.debug("cover_extender: YAML migration skipped — subentries already exist")
        return

    _LOGGER.info("cover_extender: migrating YAML config from '%s' to UI subentries", source)

    try:
        profiles, modes_list, facades, show_entities, solar_gain_global, command_interval = (
            await hass.async_add_executor_job(load_covers_config, hass, source)
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("cover_extender: YAML migration failed — could not load source: %s", err)
        return

    if not profiles and not modes_list and not facades:
        _LOGGER.warning("cover_extender: YAML migration — file empty or not found, skipping")
        return

    # ── Global subentry ───────────────────────────────────────────────────────
    global_data: dict = {
        "command_interval": int(command_interval * 1000),
        "show_sun_facing":  bool(show_entities.get("sun_facing", False)),
        "show_auto_shade":  bool(show_entities.get("auto_shade", False)),
        "show_solar_gain":  bool(show_entities.get("solar_gain", False)),
    }
    if temp_entity := solar_gain_global.get("temperature_entity"):
        global_data["sg_temperature_entity"] = temp_entity
    if (threshold := solar_gain_global.get("temperature_threshold")) is not None:
        global_data["sg_temperature_threshold"] = str(threshold)
    if weather_entity := solar_gain_global.get("weather_entity"):
        global_data["sg_weather_entity"] = weather_entity
    if conditions := solar_gain_global.get("good_conditions"):
        global_data["sg_good_conditions"] = list(conditions)

    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=global_data,
            subentry_type=SUBENTRY_TYPE_GLOBAL,
            title=await _subentry_title(hass, SUBENTRY_TYPE_GLOBAL),
            unique_id=None,
        ),
    )

    # ── Facades subentry ──────────────────────────────────────────────────────
    if facades:
        facade_items = [
            {"name": name, "azimuth": int(float(cfg.get("azimuth", 180)))}
            for name, cfg in facades.items()
        ]
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data={"items": facade_items},
                subentry_type=SUBENTRY_TYPE_FACADE,
                title=await _subentry_title(hass, SUBENTRY_TYPE_FACADE),
                unique_id=None,
            ),
        )

    # ── Modes subentry ────────────────────────────────────────────────────────
    if modes_list:
        mode_items = [
            {
                "name":     name,
                "icon":     cfg.get("icon",     "mdi:help-circle"),
                "color":    cfg.get("color",    "#FFFFFF"),
                "lock":     bool(cfg.get("lock",    False)),
                "behavior": cfg.get("behavior") or None,
                "hidden":   bool(cfg.get("hidden",  False)),
            }
            for name, cfg in modes_list.items()
        ]
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data={"items": mode_items},
                subentry_type=SUBENTRY_TYPE_MODE,
                title=await _subentry_title(hass, SUBENTRY_TYPE_MODE),
                unique_id=None,
            ),
        )

    # ── Covers subentry ───────────────────────────────────────────────────────
    if profiles:
        cover_items = []
        for entity_id, cfg in profiles.items():
            from .const import (
                CONF_FACADE, CONF_ENTITY_PICTURE,
                CONF_ANGLE_LEFT, CONF_ANGLE_RIGHT,
                CONF_MODES, CONF_SHADING, CONF_SOLAR_GAIN, CONF_EXCLUSION,
            )
            shade = cfg.get(CONF_SHADING) or {}
            sg    = cfg.get(CONF_SOLAR_GAIN) or {}
            # Convert coordinator modes format (int|None) → UI format
            modes_ui: dict = {}
            for mode_name, val in (cfg.get(CONF_MODES) or {}).items():
                if isinstance(val, int):
                    modes_ui[mode_name] = {"type": "fixed", "value": val}
                else:
                    modes_ui[mode_name] = {"type": "auto"}

            cover_items.append({
                "entity_id":                entity_id,
                "entity_picture":           cfg.get(CONF_ENTITY_PICTURE) or "",
                "facade":                   cfg.get(CONF_FACADE) or "",
                "template":                 "",
                "exclusion":                list(cfg.get(CONF_EXCLUSION) or []),
                "angle_left":               float(cfg.get(CONF_ANGLE_LEFT,  85)),
                "angle_right":              float(cfg.get(CONF_ANGLE_RIGHT, 85)),
                "shade_enable":             bool(shade.get("enable",           False)),
                "solar_gain_enable":        bool(sg.get("enable",             False)),
                "shade_distance":           float(shade.get("distance",        0.4)),
                "shade_max_height":         float(shade.get("max_height",      1.8)),
                "shade_min_height":         float(shade.get("min_height",      0.0)),
                "shade_degrees":            float(shade.get("degrees",         90)),
                "shade_min_elevation":      float(shade.get("min_elevation",   5)),
                "shade_max_elevation":      float(shade.get("max_elevation",   90)),
                "shade_minimum_position":   float(shade.get("minimum_position",15)),
                "shade_default_position":   float(shade.get("default_position",100)),
                "shade_change_threshold":   float(shade.get("change_threshold",5)),
                "shade_time_out":           float(shade.get("time_out",        2)),
                "solar_gain_position_solar":int(sg.get("position_solar",       100)),
                "solar_gain_position_cold": int(sg.get("position_cold",        0)),
                "modes":                    modes_ui,
            })

        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data={"items": cover_items},
                subentry_type=SUBENTRY_TYPE_COVER,
                title=await _subentry_title(hass, SUBENTRY_TYPE_COVER),
                unique_id=None,
            ),
        )

    # Clear the source so the migration never runs again
    hass.config_entries.async_update_entry(entry, data={})

    _LOGGER.info(
        "cover_extender: YAML migration complete — %d cover(s), %d mode(s), %d facade(s)",
        len(profiles), len(modes_list), len(facades),
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Import existing YAML configuration as a config entry (backward compat)."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cover_extender from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # One-time migration: YAML source → UI subentries (runs only if entry has
    # a CONF_SOURCE key and no subentries yet).
    await _async_migrate_yaml_to_subentries(hass, entry)

    # Remove empty singleton subentries left by old code before the coordinator
    # registers its listener — avoids spurious reload triggers.
    _cleanup_empty_singletons(hass)
    await _async_sync_subentry_titles(hass, entry)

    coordinator = CoverExtenderCoordinator(hass, entry)
    hass.data[DOMAIN]["coordinator"] = coordinator

    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _cover_only = vol.Schema({vol.Required("entity_id"): cv.entity_ids})

    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_MODE, coordinator.service_apply_mode,
        schema=vol.Schema({
            vol.Required("mode"):      cv.string,
            vol.Required("entity_id"): cv.entity_ids,
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD, coordinator.service_reload,
        schema=vol.Schema({}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_MODE_POSITION, coordinator.service_get_mode_position,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("mode"):      cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPUTE_SHADE_POSITION, coordinator.service_compute_shade_position,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_id}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_COVER_POSITION, coordinator.service_set_cover_position,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_ids,
            vol.Required("position"):  vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_OPEN_COVER,  coordinator.service_open_cover,  schema=_cover_only
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLOSE_COVER, coordinator.service_close_cover, schema=_cover_only
    )
    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_MEMORY, coordinator.service_apply_memory,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_ids}),
    )

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove persisted storage when the entry is deleted."""
    from homeassistant.helpers.storage import Store
    from .const import STORAGE_KEY, STORAGE_VERSION
    await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a cover_extender config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: CoverExtenderCoordinator | None = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_stop()
        hass.data[DOMAIN].pop("coordinator", None)
        for service in (
            SERVICE_APPLY_MODE, SERVICE_RELOAD, SERVICE_GET_MODE_POSITION,
            SERVICE_COMPUTE_SHADE_POSITION, SERVICE_SET_COVER_POSITION,
            SERVICE_OPEN_COVER, SERVICE_CLOSE_COVER, SERVICE_APPLY_MEMORY,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok
