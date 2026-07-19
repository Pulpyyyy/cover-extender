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

Configuration is done entirely through the UI (config subentries): facades,
modes, templates, covers and global settings.

Module layout:
  __init__.py     thin entry points (async_setup_entry / async_unload_entry)
  coordinator.py  CoverExtenderCoordinator — all business logic
  schemas.py      Voluptuous schemas + subentry → profiles builder
  shade.py        Solar geometry helpers (compute_shade_sync, compute_sun_facing …)
  helpers.py      Stateless attribute/position helpers

Available services:
  - cover_extender.apply_mode(mode, entity_id)         apply a mode to one or more covers
  - cover_extender.set_cover_position(entity_id, pos)  move cover(s), respecting the lock
  - cover_extender.open_cover / close_cover             open/close cover(s), respecting lock
  - cover_extender.apply_memory(entity_id)             force-apply stored memory position
  - cover_extender.compute_shade_position(entity_id)   compute solar shade position
  - cover_extender.get_mode_position(entity_id, mode)  return the position set for a mode
  - cover_extender.reload                              reload config without restarting HA
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import (
    DOMAIN,
    SERVICE_APPLY_MODE,
    SERVICE_GET_MODE_POSITION,
    SERVICE_COMPUTE_SHADE_POSITION,
    SERVICE_SET_COVER_POSITION,
    SERVICE_OPEN_COVER,
    SERVICE_CLOSE_COVER,
    SERVICE_APPLY_MEMORY,
    SERVICE_RELOAD,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_FACADE,
    SUBENTRY_TYPE_GLOBAL,
    SUBENTRY_TYPE_MODE,
    SUBENTRY_TYPE_TEMPLATE,
)
from .coordinator import CoverExtenderCoordinator
from .helpers import _subentry_title, HELPER_UNIQUE_ID_TEMPLATES, cover_object_id

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


def _migrate_helper_unique_ids(
    registry: er.EntityRegistry, legacy_keys: set[str], registry_id: str
) -> None:
    """Migrate helper entities from name-based to registry-id based unique_ids.

    Idempotent: does nothing when the helper is already on the new scheme.
    The helpers keep their entity_id, name, area and history — only the
    internal unique_id changes.
    """
    for domain, uid_tpl in HELPER_UNIQUE_ID_TEMPLATES.values():
        new_uid = uid_tpl.format(registry_id)
        if registry.async_get_entity_id(domain, DOMAIN, new_uid):
            continue  # already migrated
        for legacy_key in legacy_keys:
            legacy_uid = uid_tpl.format(legacy_key)
            if legacy_uid == new_uid:
                continue
            helper_eid = registry.async_get_entity_id(domain, DOMAIN, legacy_uid)
            if helper_eid:
                _LOGGER.debug(
                    "cover_extender: migrating unique_id of %s: %s → %s",
                    helper_eid, legacy_uid, new_uid,
                )
                registry.async_update_entity(helper_eid, new_unique_id=new_uid)
                break


def _migrate_registry_ids(hass: HomeAssistant) -> None:
    """One-time, idempotent migration to registry-id based cover references.

    - Adds entity_registry_id to every cover item (immutable link to the cover).
    - Re-syncs the stored entity_id when the cover was renamed while the
      integration was not loaded (resolved through the stored registry id).
    - Migrates the helper entities' unique_ids to the registry-id scheme.
    Covers without a registry entry keep the legacy name-based behaviour.
    """
    registry = er.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        for sub in entry.subentries.values():
            if sub.subentry_type != SUBENTRY_TYPE_COVER or "items" not in sub.data:
                continue
            items = [dict(it) for it in sub.data["items"]]
            changed = False
            for it in items:
                stored_eid: str = it.get("entity_id") or ""
                if not stored_eid:
                    continue
                reg = registry.async_get(stored_eid)
                if reg is None and (rid := it.get("entity_registry_id")):
                    # Cover renamed while the integration was not loaded
                    reg = registry.async_get(rid)
                if reg is None:
                    continue  # cover not in the registry — legacy behaviour
                # Legacy unique_ids may be based on the stored OR current name
                legacy_keys = {cover_object_id(stored_eid), cover_object_id(reg.entity_id)}
                # Cover deleted and re-created (e.g. platform swap): the stored
                # registry id no longer matches — migrate helpers keyed on it too,
                # otherwise duplicate *_2 helpers get created.
                if (old_rid := it.get("entity_registry_id")) and old_rid != reg.id:
                    legacy_keys.add(old_rid)
                _migrate_helper_unique_ids(registry, legacy_keys, reg.id)
                if it.get("entity_registry_id") != reg.id:
                    it["entity_registry_id"] = reg.id
                    changed = True
                if it.get("entity_id") != reg.entity_id:
                    _LOGGER.info(
                        "cover_extender: cover renamed %s → %s, config re-synced",
                        stored_eid, reg.entity_id,
                    )
                    it["entity_id"] = reg.entity_id
                    changed = True
            if changed:
                hass.config_entries.async_update_subentry(entry, sub, data={"items": items})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cover_extender from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Remove empty singleton subentries left by old code before the coordinator
    # registers its listener — avoids spurious reload triggers.
    _cleanup_empty_singletons(hass)
    await _async_sync_subentry_titles(hass, entry)
    # Migrate cover references and helper unique_ids to the registry-id scheme
    # BEFORE platforms are set up (they build unique_ids from the stable key).
    _migrate_registry_ids(hass)

    coordinator = CoverExtenderCoordinator(hass, entry)
    entry.runtime_data = coordinator

    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Services declared with `target:` in services.yaml receive entity_id /
    # device_id / area_id / label_id keys — the schema must accept them all;
    # the coordinator resolves them via async_extract_entity_ids.
    _cover_target = vol.Schema({**cv.TARGET_SERVICE_FIELDS})

    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_MODE, coordinator.service_apply_mode,
        schema=vol.Schema({
            **cv.TARGET_SERVICE_FIELDS,
            vol.Required("mode"): cv.string,
        }),
        supports_response=SupportsResponse.OPTIONAL,
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
            **cv.TARGET_SERVICE_FIELDS,
            vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_OPEN_COVER,  coordinator.service_open_cover,  schema=_cover_target
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLOSE_COVER, coordinator.service_close_cover, schema=_cover_target
    )
    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_MEMORY, coordinator.service_apply_memory,
        schema=_cover_target,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD, coordinator.service_reload,
        schema=vol.Schema({}),
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
        coordinator: CoverExtenderCoordinator | None = getattr(entry, "runtime_data", None)
        if coordinator:
            await coordinator.async_stop()
        entry.runtime_data = None
        for service in (
            SERVICE_APPLY_MODE, SERVICE_GET_MODE_POSITION,
            SERVICE_COMPUTE_SHADE_POSITION, SERVICE_SET_COVER_POSITION,
            SERVICE_OPEN_COVER, SERVICE_CLOSE_COVER, SERVICE_APPLY_MEMORY,
            SERVICE_RELOAD,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok
