"""Select platform for cover_extender.

Automatically creates a select.mode_<cover> entity for each configured cover,
and a global select.cover_extender_modes entity listing all defined modes.
"""
from __future__ import annotations
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, DATA_COVER_PROFILES, DATA_MODES, DATA_SELECT_COVER_IDS,
    CONF_MODES, SIGNAL_COVER_RELOAD,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up select entities from a config entry."""
    modes_list: dict = hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
    profiles: dict = hass.data.get(DOMAIN, {}).get(DATA_COVER_PROFILES, {})
    cover_entities = [
        CoverModeSelect(cover_entity_id, cfg, modes_list)
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
            async_add_entities([CoverModeSelect(eid, new_profiles[eid], new_modes_list) for eid in added])
            hass.data[DOMAIN][DATA_SELECT_COVER_IDS] = known | added
            _LOGGER.info("cover_extender select: %d entity/entities added", len(added))

        if removed:
            registry = er.async_get(hass)
            for cover_id in removed:
                cover_name = cover_id.split(".")[1]
                eid = registry.async_get_entity_id("select", DOMAIN, f"{DOMAIN}_select_mode_{cover_name}")
                if eid:
                    registry.async_remove(eid)
            hass.data[DOMAIN][DATA_SELECT_COVER_IDS] = known - removed
            _LOGGER.info("cover_extender select: %d entity/entities removed", len(removed))

    async_dispatcher_connect(hass, SIGNAL_COVER_RELOAD, _handle_platform_reload)
    return True


class CoverModeSelect(SelectEntity, RestoreEntity):
    """Mode selector for a cover."""

    def __init__(self, cover_entity_id: str, cfg: dict, modes_list: dict) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()

        self.entity_id = f"select.mode_{cover_name}"
        self._attr_unique_id = f"{DOMAIN}_select_mode_{cover_name}"
        self._attr_has_entity_name = True
        self._attr_translation_key = "mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

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
                    "icon":       modes_list.get(opt, {}).get("icon",       "mdi:help-circle"),
                    "color":      modes_list.get(opt, {}).get("color",      "white"),
                    "lock":       modes_list.get(opt, {}).get("lock",       False),
                    "auto_shade": modes_list.get(opt, {}).get("auto_shade", False),
                    "solar_gain": modes_list.get(opt, {}).get("solar_gain", False),
                }
                for opt in self._attr_options
            },
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option and sync auto switches with mode properties."""
        self._attr_current_option = option
        self.async_write_ha_state()

        modes_list: dict = self.hass.data.get(DOMAIN, {}).get(DATA_MODES, {})
        mode_props = modes_list.get(option, {})
        cover_name = self._cover_entity_id.split(".")[1]

        switch_map = {
            f"switch.{cover_name}_auto_shade":       mode_props.get("auto_shade", False),
            f"switch.{cover_name}_auto_solar_gain":  mode_props.get("solar_gain", False),
            f"switch.{cover_name}_lock":             mode_props.get("lock", False),
        }

        for switch_entity_id, should_be_on in switch_map.items():
            state = self.hass.states.get(switch_entity_id)
            if state is None:
                continue
            current_on = state.state == "on"
            if should_be_on and not current_on:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": switch_entity_id}, blocking=True
                )
            elif not should_be_on and current_on:
                await self.hass.services.async_call(
                    "switch", "turn_off", {"entity_id": switch_entity_id}, blocking=True
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Cover Extender",
            entry_type=DeviceEntryType.SERVICE,
        )

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
                    "icon":       props.get("icon",       "mdi:help-circle"),
                    "color":      props.get("color",      "white"),
                    "lock":       props.get("lock",       False),
                    "auto_shade": props.get("auto_shade", False),
                    "solar_gain": props.get("solar_gain", False),
                }
                for name, props in modes_list.items()
                if not props.get("hidden", False)
            },
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option
        self.async_write_ha_state()
