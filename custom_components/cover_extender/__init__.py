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

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
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
)
from .coordinator import CoverExtenderCoordinator
from .schemas import CONFIG_SCHEMA  # noqa: F401  (re-exported for HA schema discovery)

PLATFORMS = ["select", "switch", "binary_sensor"]


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
