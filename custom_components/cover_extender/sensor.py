"""Sensor platform for cover_extender: the day's schedule times.

  sensor.cx_morning_opening   today's morning opening (timestamp)
  sensor.cx_evening_closing   today's evening closing (timestamp)

Created only while the house has a schedule (Schedules tab of the panel),
on the integration's own device.
"""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_COVER_RELOAD, SIGNAL_SCHEDULE
from .entity import hub_device_info, sync_schedule_entities

# kind -> (entity_id, unique_id, name, key in the coordinator's schedule state)
SENSORS = {
    "morning": ("sensor.cx_morning_opening", f"{DOMAIN}_sensor_cx_morning_opening", "CX morning opening", "opening"),
    "evening": ("sensor.cx_evening_closing", f"{DOMAIN}_sensor_cx_evening_closing", "CX evening closing", "closing"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data

    def build() -> list[ScheduleTimeSensor]:
        return [ScheduleTimeSensor(coordinator, kind) for kind in SENSORS]

    sync = sync_schedule_entities(hass, coordinator, "sensor", [s[1] for s in SENSORS.values()],
                                  build, async_add_entities)
    sync()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_COVER_RELOAD, sync))


class ScheduleTimeSensor(SensorEntity):
    """Today's time of one schedule."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True

    def __init__(self, coordinator, kind: str) -> None:
        self._coordinator = coordinator
        entity_id, unique_id, name, key = SENSORS[kind]
        self.entity_id = entity_id
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = hub_device_info()
        self._attr_icon = "mdi:weather-sunset-up" if kind == "morning" else "mdi:weather-sunset-down"
        self._key = key

    @property
    def native_value(self) -> datetime | None:
        state = self._coordinator.schedule_state()
        return state.get(self._key) if state else None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SCHEDULE, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
