"""Select platform for cover_extender.

Automatically creates a select.mode_<cover> entity for each configured cover,
and a global select.cover_extender_modes entity listing all defined modes.
"""
from __future__ import annotations
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, DATA_COVER_PROFILES, DATA_MODES, DATA_SELECT_COVER_IDS,
    CONF_MODES, SIGNAL_COVER_RELOAD,
)
from .helpers import (
    cover_stable_key,
    helper_unique_id,
    purge_helper_entity,
    resolve_helper_entity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    coordinator = entry.runtime_data
    modes_list: dict = hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
    profiles: dict = hass.data.get(DOMAIN, {}).get(DATA_COVER_PROFILES, {})
    cover_entities = [
        CoverModeSelect(
            cover_entity_id, cfg, modes_list, coordinator,
            cover_stable_key(hass, cover_entity_id),
        )
        for cover_entity_id, cfg in profiles.items()
        if cfg.get(CONF_MODES)
    ]
    hass.data[DOMAIN][DATA_SELECT_COVER_IDS] = {e._cover_entity_id for e in cover_entities}
    entities = [CoverModesGlobalSelect(modes_list)] + cover_entities
    _LOGGER.info("cover_extender: created %d select entities", len(entities))
    async_add_entities(entities)

    @callback
    def _handle_platform_reload() -> None:
        """Add select entities for new covers, remove entities for deleted covers."""
        new_profiles: dict = hass.data[DOMAIN].get(DATA_COVER_PROFILES, {})
        known: set[str] = hass.data[DOMAIN].get(DATA_SELECT_COVER_IDS, set())

        added = {
            eid for eid, cfg in new_profiles.items()
            if eid not in known and cfg.get(CONF_MODES)
        }
        removed = known - set(new_profiles)

        if added:
            new_modes_list: dict = hass.data[DOMAIN].get(DATA_MODES, {})
            async_add_entities([
                CoverModeSelect(
                    eid, new_profiles[eid], new_modes_list, coordinator,
                    cover_stable_key(hass, eid),
                )
                for eid in added
            ])
            hass.data[DOMAIN][DATA_SELECT_COVER_IDS] = known | added
            _LOGGER.info("cover_extender select: %d entity/entities added", len(added))

        if removed:
            for cover_id in removed:
                purge_helper_entity(hass, cover_id, "select_mode")
            hass.data[DOMAIN][DATA_SELECT_COVER_IDS] = known - removed
            _LOGGER.info("cover_extender select: %d entity/entities removed", len(removed))

    async_dispatcher_connect(hass, SIGNAL_COVER_RELOAD, _handle_platform_reload)


class CoverModeSelect(SelectEntity, RestoreEntity):
    """Mode selector for a cover."""

    def __init__(
        self, cover_entity_id: str, cfg: dict, modes_list: dict, coordinator,
        stable_key: str,
    ) -> None:
        self._cover_entity_id = cover_entity_id
        self._coordinator = coordinator
        cover_name = cover_entity_id.split(".")[1]

        # entity_id stays name-based (human-facing suggestion); the unique_id
        # uses the cover's stable key so renaming the cover breaks nothing.
        self.entity_id = f"select.mode_{cover_name}"
        self._attr_unique_id = helper_unique_id("select_mode", stable_key)
        self._attr_has_entity_name = True
        self._attr_translation_key = "mode"

        modes: dict = cfg.get(CONF_MODES, {})
        self._attr_options = list(modes)
        self._attr_current_option = self._attr_options[0] if self._attr_options else None

    async def async_added_to_hass(self) -> None:
        """Restore last known state and subscribe to reloads."""
        if (last_state := await self.async_get_last_state()) and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            self.async_write_ha_state()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_COVER_RELOAD, self._handle_reload)
        )

    @callback
    def _handle_reload(self) -> None:
        """Update options from reloaded profiles."""
        profiles: dict = self.hass.data.get(DOMAIN, {}).get(DATA_COVER_PROFILES, {})
        cfg = profiles.get(self._cover_entity_id, {})
        new_options = list(cfg.get(CONF_MODES, {}))
        if new_options == self._attr_options:
            return
        self._attr_options = new_options
        if self._attr_current_option not in new_options:
            self._attr_current_option = new_options[0] if new_options else None
            _LOGGER.info(
                "%s: current option reset to '%s' after reload",
                self.entity_id, self._attr_current_option,
            )
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        """Return the icon of the current mode."""
        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        return modes_list.get(self._attr_current_option or "", {}).get("icon", "mdi:help-circle-outline")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose icon, color of the current mode, and the full available modes dict."""
        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        display = modes_list.get(self._attr_current_option or "", {})
        return {
            "icon":  display.get("icon",  "mdi:refresh-auto"),
            "color": display.get("color", "white"),
            "modes_list": {
                opt: {
                    "icon":     modes_list.get(opt, {}).get("icon",     "mdi:help-circle"),
                    "color":    modes_list.get(opt, {}).get("color",    "white"),
                    "lock":     modes_list.get(opt, {}).get("lock",     False),
                    "behavior": modes_list.get(opt, {}).get("behavior", None),
                }
                for opt in self._attr_options
            },
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option and immediately sync the lock switch.

        The coordinator (_handle_select_mode_change → _apply_mode_core) handles the
        full mode logic (lock, behavior, position, memory) asynchronously.  We also
        apply the lock here synchronously so the UI reflects the new state without
        waiting for the coordinator task to be scheduled.
        """
        self._attr_current_option = option
        self.async_write_ha_state()

        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        mode_props = modes_list.get(option, {})
        lock_id = resolve_helper_entity(self.hass, self._cover_entity_id, "lock")
        should_lock = mode_props.get("lock", False)

        state = self.hass.states.get(lock_id)
        if state is not None:
            current_on = state.state == "on"
            if should_lock and not current_on:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": lock_id}, blocking=True
                )
            elif not should_lock and current_on:
                # Mode-driven unlock: let the coordinator's _apply_mode_core own the
                # memory/position decision instead of its _handle_lock_off listener
                # (which can't see the target mode's fixed position). Cleared by
                # _apply_mode_core, and consumed one-shot by _handle_lock_off.
                if self._coordinator is not None:
                    self._coordinator._suspend_lock_off.add(self._cover_entity_id)
                await self.hass.services.async_call(
                    "switch", "turn_off", {"entity_id": lock_id}, blocking=True
                )


class CoverModesGlobalSelect(SelectEntity, RestoreEntity):
    """Global selector exposing all modes defined in cover_extender_modes.

    Options and icon/color are updated dynamically on every reload.
    """

    def __init__(self, modes_list: dict) -> None:
        self._attr_unique_id = f"{DOMAIN}_select_cover_extender_modes"
        self.entity_id = "select.cover_extender_modes"
        self._attr_has_entity_name = True
        self._attr_translation_key = "cover_extender_modes"
        self._attr_options = [m for m, p in modes_list.items() if not p.get("hidden", False)]
        self._attr_current_option = self._attr_options[0] if self._attr_options else None

    async def async_added_to_hass(self) -> None:
        """Restore last known state and subscribe to reloads."""
        if (last_state := await self.async_get_last_state()) and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            self.async_write_ha_state()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_COVER_RELOAD, self._handle_reload)
        )

    @callback
    def _handle_reload(self) -> None:
        """Update options from reloaded cover_extender_modes."""
        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        new_options = [m for m, p in modes_list.items() if not p.get("hidden", False)]
        if new_options == self._attr_options:
            return
        self._attr_options = new_options
        if self._attr_current_option not in new_options:
            self._attr_current_option = new_options[0] if new_options else None
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        """Icon of the current mode."""
        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        return modes_list.get(self._attr_current_option or "", {}).get("icon", "mdi:help-circle-outline")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose icon/color of the current mode and the full modes dict."""
        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        display = modes_list.get(self._attr_current_option or "", {})
        return {
            "icon":  display.get("icon",  "mdi:refresh-auto"),
            "color": display.get("color", "white"),
            "modes_list": {
                name: {
                    "icon":     props.get("icon",     "mdi:help-circle"),
                    "color":    props.get("color",    "white"),
                    "lock":     props.get("lock",     False),
                    "behavior": props.get("behavior", None),
                }
                for name, props in modes_list.items()
                if not props.get("hidden", False)
            },
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option
        self.async_write_ha_state()
