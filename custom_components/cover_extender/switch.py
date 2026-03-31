"""Switch platform for cover_extender.

Automatically creates:
  - switch.<cover>_lock        for every configured cover
  - switch.<cover>_auto_shade  for covers with shade.enable: true
"""
from __future__ import annotations
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, DATA_COVER_PROFILES,
    DATA_SWITCH_COVER_IDS, DATA_SWITCH_AUTO_SHADE_IDS, DATA_SWITCH_AUTO_SOLAR_GAIN_IDS,
    CONF_SHADING, CONF_SOLAR_GAIN, SIGNAL_COVER_RELOAD,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from a config entry."""
    profiles: dict = hass.data.get(DOMAIN, {}).get(DATA_COVER_PROFILES, {})

    lock_entities = [CoverLockSwitch(eid) for eid in profiles]
    hass.data[DOMAIN][DATA_SWITCH_COVER_IDS] = {e._cover_entity_id for e in lock_entities}

    auto_shade_entities = [
        CoverShadingAutoSwitch(eid)
        for eid, cfg in profiles.items()
        if cfg.get(CONF_SHADING, {}).get("enable", False)
    ]
    hass.data[DOMAIN][DATA_SWITCH_AUTO_SHADE_IDS] = {e._cover_entity_id for e in auto_shade_entities}

    auto_solar_gain_entities = [
        CoverSolarGainAutoSwitch(eid)
        for eid, cfg in profiles.items()
        if cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False)
    ]
    hass.data[DOMAIN][DATA_SWITCH_AUTO_SOLAR_GAIN_IDS] = {e._cover_entity_id for e in auto_solar_gain_entities}

    all_entities = lock_entities + auto_shade_entities + auto_solar_gain_entities
    _LOGGER.info(
        "cover_extender: created %d switch entities (%d auto_shade, %d auto_solar_gain)",
        len(all_entities), len(auto_shade_entities), len(auto_solar_gain_entities),
    )
    async_add_entities(all_entities)

    @callback
    def _handle_platform_reload() -> None:
        """Add switch entities for new covers, remove entities for deleted covers."""
        new_profiles: dict = hass.data[DOMAIN].get(DATA_COVER_PROFILES, {})

        # --- Locks ---
        known_lock: set[str] = hass.data[DOMAIN].get(DATA_SWITCH_COVER_IDS, set())
        added_lock = set(new_profiles) - known_lock
        removed_lock = known_lock - set(new_profiles)

        if added_lock:
            async_add_entities([CoverLockSwitch(eid) for eid in added_lock])
            hass.data[DOMAIN][DATA_SWITCH_COVER_IDS] = known_lock | added_lock

        if removed_lock:
            registry = er.async_get(hass)
            for cover_id in removed_lock:
                cover_name = cover_id.split(".")[1]
                eid = registry.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_switch_{cover_name}_lock")
                if eid:
                    registry.async_remove(eid)
            hass.data[DOMAIN][DATA_SWITCH_COVER_IDS] = known_lock - removed_lock

        # --- Auto shade ---
        known_auto_shade: set[str] = hass.data[DOMAIN].get(DATA_SWITCH_AUTO_SHADE_IDS, set())
        should_have = {eid for eid, cfg in new_profiles.items() if cfg.get(CONF_SHADING, {}).get("enable", False)}
        added_auto_shade = should_have - known_auto_shade
        removed_auto_shade = known_auto_shade - should_have

        if added_auto_shade:
            async_add_entities([CoverShadingAutoSwitch(eid) for eid in added_auto_shade])
            hass.data[DOMAIN][DATA_SWITCH_AUTO_SHADE_IDS] = known_auto_shade | added_auto_shade

        if removed_auto_shade:
            registry = er.async_get(hass)
            for cover_id in removed_auto_shade:
                cover_name = cover_id.split(".")[1]
                eid = registry.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_switch_{cover_name}_auto_shade")
                if eid:
                    registry.async_remove(eid)
            hass.data[DOMAIN][DATA_SWITCH_AUTO_SHADE_IDS] = known_auto_shade - removed_auto_shade

        # --- Auto solar gain ---
        known_auto_solar_gain: set[str] = hass.data[DOMAIN].get(DATA_SWITCH_AUTO_SOLAR_GAIN_IDS, set())
        should_have_solar_gain = {eid for eid, cfg in new_profiles.items() if cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False)}
        added_auto_solar_gain = should_have_solar_gain - known_auto_solar_gain
        removed_auto_solar_gain = known_auto_solar_gain - should_have_solar_gain

        if added_auto_solar_gain:
            async_add_entities([CoverSolarGainAutoSwitch(eid) for eid in added_auto_solar_gain])
            hass.data[DOMAIN][DATA_SWITCH_AUTO_SOLAR_GAIN_IDS] = known_auto_solar_gain | added_auto_solar_gain

        if removed_auto_solar_gain:
            registry = er.async_get(hass)
            for cover_id in removed_auto_solar_gain:
                cover_name = cover_id.split(".")[1]
                eid = registry.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_switch_{cover_name}_auto_solar_gain")
                if eid:
                    registry.async_remove(eid)
            hass.data[DOMAIN][DATA_SWITCH_AUTO_SOLAR_GAIN_IDS] = known_auto_solar_gain - removed_auto_solar_gain

        if added_lock or removed_lock or added_auto_shade or removed_auto_shade or added_auto_solar_gain or removed_auto_solar_gain:
            _LOGGER.info(
                "cover_extender switch reload: +%d/-%d locks, +%d/-%d auto_shade, +%d/-%d auto_solar_gain",
                len(added_lock), len(removed_lock),
                len(added_auto_shade), len(removed_auto_shade),
                len(added_auto_solar_gain), len(removed_auto_solar_gain),
            )

    async_dispatcher_connect(hass, SIGNAL_COVER_RELOAD, _handle_platform_reload)


class CoverLockSwitch(SwitchEntity, RestoreEntity):
    """Automation lock for a cover."""

    def __init__(self, cover_entity_id: str) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()

        self.entity_id = f"switch.{cover_name}_lock"
        self._attr_unique_id = f"{DOMAIN}_switch_{cover_name}_lock"
        self._attr_has_entity_name = True
        self._attr_translation_key = "lock"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Restore last known state after restart."""
        if last_state := await self.async_get_last_state():
            self._attr_is_on = last_state.state == "on"
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Lock the cover."""
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Unlock the cover."""
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        return "mdi:lock" if self._attr_is_on else "mdi:lock-open-variant"

    @property
    def extra_state_attributes(self) -> dict:
        """Expose lock color for custom cards."""
        if self._attr_is_on:
            return {"icon_color": "red"}
        return {"icon_color": "disabled"}


class CoverShadingAutoSwitch(SwitchEntity, RestoreEntity):
    """Autonomous solar shade switch for a cover.

    When on, cover_extender computes and applies the shade position
    on every sun.sun state change, without a blueprint.
    """

    def __init__(self, cover_entity_id: str) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()

        self.entity_id = f"switch.{cover_name}_auto_shade"
        self._attr_unique_id = f"{DOMAIN}_switch_{cover_name}_auto_shade"
        self._attr_has_entity_name = True
        self._attr_translation_key = "auto_shade"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        if last_state := await self.async_get_last_state():
            self._attr_is_on = last_state.state == "on"
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        return "mdi:sun-clock-outline" if self._attr_is_on else "mdi:weather-sunny-off"

    @property
    def extra_state_attributes(self) -> dict:
        if self._attr_is_on:
            return {"icon_color": "amber"}
        return {"icon_color": "disabled"}


class CoverSolarGainAutoSwitch(SwitchEntity, RestoreEntity):
    """Solar gain temperature-tracking switch for a cover.

    When on, cover_extender applies position_solar or position_cold based on
    temperature, sun facing, and weather conditions.
    Turned on automatically when a mode with solar_gain: true is applied.
    """

    def __init__(self, cover_entity_id: str) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()

        self.entity_id = f"switch.{cover_name}_auto_solar_gain"
        self._attr_unique_id = f"{DOMAIN}_switch_{cover_name}_auto_solar_gain"
        self._attr_has_entity_name = True
        self._attr_translation_key = "auto_solar_gain"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        if last_state := await self.async_get_last_state():
            self._attr_is_on = last_state.state == "on"
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        return "mdi:thermometer-sun" if self._attr_is_on else "mdi:thermometer-off"

    @property
    def extra_state_attributes(self) -> dict:
        if self._attr_is_on:
            return {"icon_color": "orange"}
        return {"icon_color": "disabled"}
