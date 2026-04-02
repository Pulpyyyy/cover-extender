"""Binary sensor platform for cover_extender.

Exposes sun_facing, auto_shade and solar_gain as binary_sensor entities,
controlled by the show_entities: section of the YAML config file.

  show_entities:
    sun_facing: true    →  binary_sensor.<cover>_sun_facing
    auto_shade: true    →  binary_sensor.<cover>_auto_shade
    solar_gain: true    →  binary_sensor.<cover>_solar_gain

All default to false — no binary_sensors are created unless explicitly enabled.
"""
from __future__ import annotations
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_SHOW_ENTITIES,
    DATA_BINARY_SENSOR_SUN_FACING_IDS,
    DATA_BINARY_SENSOR_AUTO_SHADE_IDS,
    DATA_BINARY_SENSOR_AUTO_SOLAR_GAIN_IDS,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
    CONF_FACADE,
    ATTR_SOLEIL_EN_FACE,
    SIGNAL_COVER_RELOAD,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary_sensor entities from a config entry."""
    profiles: dict = hass.data.get(DOMAIN, {}).get(DATA_COVER_PROFILES, {})
    show_entities: dict = hass.data.get(DOMAIN, {}).get(DATA_SHOW_ENTITIES, {})

    sun_facing_entities, auto_shade_entities, solar_gain_entities = _build_entities(profiles, show_entities)

    hass.data[DOMAIN][DATA_BINARY_SENSOR_SUN_FACING_IDS] = {
        e.cover_entity_id for e in sun_facing_entities
    }
    hass.data[DOMAIN][DATA_BINARY_SENSOR_AUTO_SHADE_IDS] = {
        e.cover_entity_id for e in auto_shade_entities
    }
    hass.data[DOMAIN][DATA_BINARY_SENSOR_AUTO_SOLAR_GAIN_IDS] = {
        e.cover_entity_id for e in solar_gain_entities
    }

    all_entities = sun_facing_entities + auto_shade_entities + solar_gain_entities
    _LOGGER.info(
        "cover_extender: created %d binary_sensor entities (%d sun_facing, %d auto_shade, %d solar_gain)",
        len(all_entities), len(sun_facing_entities), len(auto_shade_entities), len(solar_gain_entities),
    )
    async_add_entities(all_entities)

    @callback
    def _handle_platform_reload() -> None:
        """Synchronise binary_sensors after a config reload."""
        new_profiles: dict = hass.data[DOMAIN].get(DATA_COVER_PROFILES, {})
        new_vas: dict = hass.data[DOMAIN].get(DATA_SHOW_ENTITIES, {})

        new_sf, new_as, new_sg = _build_entities(new_profiles, new_vas)
        new_sf_ids = {e.cover_entity_id for e in new_sf}
        new_as_ids = {e.cover_entity_id for e in new_as}
        new_sg_ids = {e.cover_entity_id for e in new_sg}

        known_sf: set[str] = hass.data[DOMAIN].get(DATA_BINARY_SENSOR_SUN_FACING_IDS, set())
        known_as: set[str] = hass.data[DOMAIN].get(DATA_BINARY_SENSOR_AUTO_SHADE_IDS, set())
        known_sg: set[str] = hass.data[DOMAIN].get(DATA_BINARY_SENSOR_AUTO_SOLAR_GAIN_IDS, set())

        registry = er.async_get(hass)

        # --- sun_facing ---
        added_sf = [e for e in new_sf if e.cover_entity_id not in known_sf]
        removed_sf = known_sf - new_sf_ids
        if added_sf:
            async_add_entities(added_sf)
        for cover_id in removed_sf:
            cover_name = cover_id.split(".")[1]
            eid = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{DOMAIN}_binary_sensor_{cover_name}_sun_facing")
            if eid:
                registry.async_remove(eid)

        # --- auto_shade ---
        added_as = [e for e in new_as if e.cover_entity_id not in known_as]
        removed_as = known_as - new_as_ids
        if added_as:
            async_add_entities(added_as)
        for cover_id in removed_as:
            cover_name = cover_id.split(".")[1]
            eid = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{DOMAIN}_binary_sensor_{cover_name}_auto_shade")
            if eid:
                registry.async_remove(eid)

        # --- solar_gain ---
        added_sg = [e for e in new_sg if e.cover_entity_id not in known_sg]
        removed_sg = known_sg - new_sg_ids
        if added_sg:
            async_add_entities(added_sg)
        for cover_id in removed_sg:
            cover_name = cover_id.split(".")[1]
            eid = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{DOMAIN}_binary_sensor_{cover_name}_solar_gain")
            if eid:
                registry.async_remove(eid)

        hass.data[DOMAIN][DATA_BINARY_SENSOR_SUN_FACING_IDS] = new_sf_ids
        hass.data[DOMAIN][DATA_BINARY_SENSOR_AUTO_SHADE_IDS] = new_as_ids
        hass.data[DOMAIN][DATA_BINARY_SENSOR_AUTO_SOLAR_GAIN_IDS] = new_sg_ids

        if added_sf or removed_sf or added_as or removed_as or added_sg or removed_sg:
            _LOGGER.info(
                "cover_extender binary_sensor reload: +%d/-%d sun_facing, +%d/-%d auto_shade, +%d/-%d solar_gain",
                len(added_sf), len(removed_sf), len(added_as), len(removed_as), len(added_sg), len(removed_sg),
            )

    async_dispatcher_connect(hass, SIGNAL_COVER_RELOAD, _handle_platform_reload)


def _build_entities(
    profiles: dict,
    show_entities: dict,
) -> tuple[list, list, list]:
    """Build entity lists according to show_entities flags and profiles."""
    expose_sf = show_entities.get("sun_facing", False)
    expose_as = show_entities.get("auto_shade", False)
    expose_sg = show_entities.get("solar_gain", False)

    sun_facing_entities = []
    auto_shade_entities = []
    solar_gain_entities = []

    for cover_id, cfg in profiles.items():
        if expose_sf and cfg.get(CONF_FACADE):
            sun_facing_entities.append(CoverSunFacingBinarySensor(cover_id))
        if expose_as:
            auto_shade_entities.append(
                CoverEnableAutoShadeBinarySensor(cover_id, bool(cfg.get(CONF_SHADING, {}).get("enable", False)))
            )
        if expose_sg:
            solar_gain_entities.append(
                CoverEnableSolarGainBinarySensor(cover_id, bool(cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False)))
            )

    return sun_facing_entities, auto_shade_entities, solar_gain_entities


class CoverSunFacingBinarySensor(BinarySensorEntity):
    """Mirror of the sun_facing attribute of a cover, exposed as a binary_sensor.

    Updates on every cover state change (the sun_facing attribute is injected
    by CoverExtenderCoordinator._inject_sun_facing).
    """

    _attr_should_poll = False

    def __init__(self, cover_entity_id: str) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()

        self.entity_id = f"binary_sensor.{cover_name}_sun_facing"
        self._attr_unique_id = f"{DOMAIN}_binary_sensor_{cover_name}_sun_facing"
        self._attr_has_entity_name = True
        self._attr_translation_key = "sun_facing"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def cover_entity_id(self) -> str:
        """Entity ID of the associated cover."""
        return self._cover_entity_id

    async def async_added_to_hass(self) -> None:
        """Read initial state and subscribe to cover state changes."""
        state = self.hass.states.get(self._cover_entity_id)
        if state:
            val = state.attributes.get(ATTR_SOLEIL_EN_FACE)
            if val is not None:
                self._attr_is_on = bool(val)
                self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._cover_entity_id], self._handle_cover_change
            )
        )

    @callback
    def _handle_cover_change(self, event: Event) -> None:
        """Update state when the sun_facing attribute of the cover changes."""
        new_state = event.data.get("new_state")
        if not new_state:
            return
        val = new_state.attributes.get(ATTR_SOLEIL_EN_FACE)
        if val is None:
            return
        new_is_on = bool(val)
        if new_is_on != self._attr_is_on:
            self._attr_is_on = new_is_on
            self.async_write_ha_state()

    @property
    def icon(self) -> str:
        return "mdi:sun-angle" if self._attr_is_on else "mdi:sun-angle-outline"

    @property
    def extra_state_attributes(self) -> dict:
        return {"icon_color": "var(--primary-color)" if self._attr_is_on else "var(--disabled-color)"}


class CoverEnableAutoShadeBinarySensor(BinarySensorEntity):
    """Mirrors switch.<cover>_auto_shade state as a binary_sensor.

    Updates whenever the switch is toggled (via mode change or manually).
    """

    _attr_should_poll = False

    def __init__(self, cover_entity_id: str, auto_shade: bool) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()
        self._switch_entity_id = f"switch.{cover_name}_auto_shade"

        self.entity_id = f"binary_sensor.{cover_name}_auto_shade"
        self._attr_unique_id = f"{DOMAIN}_binary_sensor_{cover_name}_auto_shade"
        self._attr_has_entity_name = True
        self._attr_translation_key = "auto_shade"
        self._attr_is_on = auto_shade
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def cover_entity_id(self) -> str:
        """Entity ID of the associated cover."""
        return self._cover_entity_id

    async def async_added_to_hass(self) -> None:
        """Read switch initial state then track it."""
        switch_state = self.hass.states.get(self._switch_entity_id)
        if switch_state:
            self._attr_is_on = switch_state.state == "on"
            self.async_write_ha_state()

        @callback
        def _on_switch_change(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            new_val = new_state.state == "on"
            if new_val != self._attr_is_on:
                self._attr_is_on = new_val
                self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._switch_entity_id], _on_switch_change
            )
        )

    @property
    def icon(self) -> str:
        return "mdi:sun-clock" if self._attr_is_on else "mdi:sun-clock-outline"

    @property
    def extra_state_attributes(self) -> dict:
        return {"icon_color": "var(--primary-color)" if self._attr_is_on else "var(--disabled-color)"}


class CoverEnableSolarGainBinarySensor(BinarySensorEntity):
    """Mirrors switch.<cover>_auto_solar_gain state as a binary_sensor.

    Updates whenever the switch is toggled (via mode change or manually).
    """

    _attr_should_poll = False

    def __init__(self, cover_entity_id: str, solar_gain: bool) -> None:
        self._cover_entity_id = cover_entity_id
        cover_name = cover_entity_id.split(".")[1]
        friendly = cover_name.replace("_", " ").title()
        self._switch_entity_id = f"switch.{cover_name}_auto_solar_gain"

        self.entity_id = f"binary_sensor.{cover_name}_solar_gain"
        self._attr_unique_id = f"{DOMAIN}_binary_sensor_{cover_name}_solar_gain"
        self._attr_has_entity_name = True
        self._attr_translation_key = "enable_solar_gain"
        self._attr_is_on = solar_gain
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cover_entity_id)},
            name=friendly,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def cover_entity_id(self) -> str:
        """Entity ID of the associated cover."""
        return self._cover_entity_id

    async def async_added_to_hass(self) -> None:
        """Read switch initial state then track it."""
        switch_state = self.hass.states.get(self._switch_entity_id)
        if switch_state:
            self._attr_is_on = switch_state.state == "on"
            self.async_write_ha_state()

        @callback
        def _on_switch_change(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            new_val = new_state.state == "on"
            if new_val != self._attr_is_on:
                self._attr_is_on = new_val
                self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._switch_entity_id], _on_switch_change
            )
        )

    @property
    def icon(self) -> str:
        return "mdi:thermometer-sun" if self._attr_is_on else "mdi:thermometer-off"

    @property
    def extra_state_attributes(self) -> dict:
        return {"icon_color": "var(--primary-color)" if self._attr_is_on else "var(--disabled-color)"}
