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

Configuration is done entirely through the admin panel at /cover-extender and
stored in entry.options[OPT_CONFIG]: facades, modes, templates, covers and
global settings (see const.py for the layout, and async_migrate_entry below for
the v1 → v2 move out of the config subentries).

Module layout:
  __init__.py     thin entry points (async_setup_entry / async_unload_entry)
  coordinator.py  CoverExtenderCoordinator — all business logic
  schemas.py      Voluptuous schemas + options → profiles builder
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

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)

from . import frontend as admin_frontend
from .websocket_api import async_register_websocket_api
from .const import (
    DOMAIN,
    PANEL_URL_PATH,
    SERVICE_APPLY_MODE,
    SERVICE_GET_MODE_POSITION,
    SERVICE_COMPUTE_SHADE_POSITION,
    SERVICE_SET_COVER_POSITION,
    SERVICE_OPEN_COVER,
    SERVICE_CLOSE_COVER,
    SERVICE_APPLY_MEMORY,
    SERVICE_RELOAD,
    OPT_CONFIG,
    SECTION_COVER,
    SECTION_GLOBAL,
    SECTIONS_WITH_ITEMS,
)
from .coordinator import CoverExtenderCoordinator
from .helpers import HELPER_UNIQUE_ID_TEMPLATES, cover_object_id

import logging
_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["select", "switch", "binary_sensor"]

_MIGRATED_SUBENTRY_TYPES = (SECTION_GLOBAL, *SECTIONS_WITH_ITEMS)


# ── v1 → v2: config subentries → entry.options ────────────────────────────────

def _sections_from_subentries(entry: ConfigEntry) -> dict[str, Any]:
    """Lift the five singleton subentries into the OPT_CONFIG sections dict.

    Absorbs every historical shape in one pass, so nothing downstream has to
    know they existed:
      - singleton subentry  {"items": [...]}      → the list itself
      - pre-singleton, one subentry per item {...} → appended to the list
      - pre-2.0 global settings as flat entry.options keys → the global dict
    Duplicates (two non-empty subentries of the same type, which the old reader
    resolved by picking one) are collapsed on name / entity_id, first wins.
    """
    sections: dict[str, Any] = {SECTION_GLOBAL: {}}
    for key in SECTIONS_WITH_ITEMS:
        sections[key] = []

    for sub in entry.subentries.values():
        data = dict(sub.data)
        if sub.subentry_type == SECTION_GLOBAL:
            if data and not sections[SECTION_GLOBAL]:
                sections[SECTION_GLOBAL] = data
        elif sub.subentry_type in SECTIONS_WITH_ITEMS:
            items = data.get("items") if "items" in data else ([data] if data else [])
            sections[sub.subentry_type].extend(dict(it) for it in items)

    for key in SECTIONS_WITH_ITEMS:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in sections[key]:
            ident = item.get("entity_id") or item.get("name") or ""
            if ident and ident in seen:
                _LOGGER.warning(
                    "cover_extender: dropping duplicate %s %r while migrating", key, ident
                )
                continue
            seen.add(ident)
            unique.append(item)
        sections[key] = unique

    if not sections[SECTION_GLOBAL]:
        sections[SECTION_GLOBAL] = {
            k: v for k, v in (entry.options or {}).items() if k != OPT_CONFIG
        }
    return sections


def _drop_legacy_subentries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the config subentries the configuration used to live in.

    Run by the migration and again on every setup, because the migration is a
    one-way door: it writes the options and bumps the version first (losing the
    data to a crash is not an option), so a shutdown in between would leave a v2
    entry that never migrates again — and the five empty groups would sit on the
    integration page forever. Called before the coordinator registers its update
    listener, so removing them triggers no reload.
    """
    for subentry_id, sub in list(entry.subentries.items()):
        if sub.subentry_type not in _MIGRATED_SUBENTRY_TYPES:
            continue
        _LOGGER.debug(
            "cover_extender: removing migrated subentry %s (type=%s)",
            subentry_id, sub.subentry_type,
        )
        hass.config_entries.async_remove_subentry(entry, subentry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Move the configuration out of the config subentries and into the options.

    The five sections were stored as singleton subentries only because that was
    the storage the wizards wrote to. They carry no device and no entity, so the
    integration page rendered them as five empty groups — the sole reason for
    this migration. The data itself is copied verbatim.
    """
    if entry.version > 2:
        # Downgrade from a future version: refuse rather than corrupt.
        return False

    if entry.version == 1:
        sections = _sections_from_subentries(entry)
        _LOGGER.info(
            "cover_extender: migrating to entry options — %d facade(s), %d mode(s), "
            "%d cover(s), %d template(s), %d global key(s)",
            *(len(sections[k]) for k in SECTIONS_WITH_ITEMS),
            len(sections[SECTION_GLOBAL]),
        )
        # Options are replaced, not merged: the only thing that ever lived at the
        # top level was the pre-2.0 flat global block, now absorbed above.
        hass.config_entries.async_update_entry(
            entry, options={OPT_CONFIG: sections}, version=2
        )
        _drop_legacy_subentries(hass, entry)

    return True


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


def _migrate_registry_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """One-time, idempotent migration to registry-id based cover references.

    - Adds entity_registry_id to every cover item (immutable link to the cover).
    - Re-syncs the stored entity_id when the cover was renamed while the
      integration was not loaded (resolved through the stored registry id).
    - Migrates the helper entities' unique_ids to the registry-id scheme.
    Covers without a registry entry keep the legacy name-based behaviour.
    """
    registry = er.async_get(hass)
    sections = dict(entry.options.get(OPT_CONFIG) or {})
    items = [dict(it) for it in (sections.get(SECTION_COVER) or [])]
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
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, OPT_CONFIG: {**sections, SECTION_COVER: items}},
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cover_extender from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Sweep up subentries a half-applied v1 → v2 migration could have left.
    _drop_legacy_subentries(hass, entry)
    # Migrate cover references and helper unique_ids to the registry-id scheme
    # BEFORE platforms are set up (they build unique_ids from the stable key)
    # and before the coordinator registers its listener (no spurious reload).
    _migrate_registry_ids(hass, entry)

    # Admin panel: WS API (idempotent) + hidden panel + hub device whose
    # configuration_url is the standard "Configure device" path to reach it.
    async_register_websocket_api(hass)
    await admin_frontend.async_register(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "hub")},
        name="Cover Extender",
        manufacturer="Pulpyyyy",
        model="Cover Extender",
        entry_type=dr.DeviceEntryType.SERVICE,
        configuration_url=f"homeassistant://{PANEL_URL_PATH}",
    )

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
    """Remove persisted storage and the admin panel when the entry is deleted."""
    from homeassistant.helpers.storage import Store
    from .const import STORAGE_KEY, STORAGE_VERSION
    admin_frontend.async_unregister(hass)
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
