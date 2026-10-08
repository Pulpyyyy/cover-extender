"""Tests for the schedules in the coordinator and in the WebSocket validation.

The sun is synthetic (fixed 07:00 sunrise and 19:00 sunset UTC, no DST) and
"now" is pinned, so every time below is exact.
"""
from __future__ import annotations

import asyncio
import types
from datetime import datetime, timezone

import pytest

from custom_components.cover_extender import coordinator as coord_mod
from custom_components.cover_extender import websocket_api as ws
from custom_components.cover_extender.const import (
    CONF_MODES,
    CONF_SCHEDULE,
    DATA_COVER_PROFILES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_MODES,
    DATA_SOLAR_GAIN,
    DOMAIN,
    OPT_CONFIG,
    SECTION_COVER,
    SECTION_MODE,
    SECTION_SCHEDULE,
)
from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.schedule import DAYS, SunYear

UTC = timezone.utc
LIVING, BEDROOM = "cover.living_room", "cover.bedroom"
HOUSE = {
    "morning": {"type": "fixed", "time": "07:30"},
    "evening": {"type": "fixed", "time": "20:30"},
}


class FakeServices:
    def __init__(self, hass):
        self._hass = hass
        self.calls = []

    async def async_call(self, domain, service, data):
        self.calls.append((domain, service, data))
        if domain == "select":
            self._hass.states.set(data["entity_id"], data["option"])


class FakeStore:
    def __init__(self):
        self.saved = None

    def async_delay_save(self, func, *_a):
        self.saved = func()


@pytest.fixture
def coord(hass, monkeypatch):
    monkeypatch.setattr(coord_mod.er, "async_get", lambda h: h.entity_registry)
    monkeypatch.setattr(coord_mod, "Store", lambda *a, **k: FakeStore())
    timers = []
    monkeypatch.setattr(
        coord_mod, "async_track_point_in_time",
        lambda h, action, when: timers.append((action, when)) or (lambda: None),
    )
    monkeypatch.setattr(coord_mod, "async_dispatcher_send", lambda *a: None)
    hass.services = FakeServices(hass)
    hass.tasks = []
    hass.async_create_task = hass.tasks.append
    hass.bus = types.SimpleNamespace(async_fire=lambda *a: None)
    hass.config = types.SimpleNamespace(time_zone="UTC", latitude=48.8, longitude=2.3)
    entry = types.SimpleNamespace(options={OPT_CONFIG: {SECTION_SCHEDULE: dict(HOUSE)}})
    c = CoverExtenderCoordinator(hass, entry)
    c.timers = timers
    sun = SunYear(ref=[0.0] + [7 * 60.0] * DAYS, off=[0] * (DAYS + 1))
    monkeypatch.setattr(c, "_sun_year", lambda kind, year: sun)
    hass.data[DOMAIN] = {
        DATA_COVER_PROFILES: {
            LIVING: {CONF_MODES: {"Day": 100, "Night": 0}, CONF_SCHEDULE: {"morning": "Day", "evening": "Night"}},
            BEDROOM: {CONF_MODES: {"Day": 100, "Night": 0}, CONF_SCHEDULE: {"morning": None, "evening": "Night"}},
        },
        DATA_FACADES: {}, DATA_MODES: {"Day": {}, "Night": {}}, DATA_SOLAR_GAIN: {}, DATA_MEMORY: {},
    }
    hass.states.set("select.living_room_cx_mode", "Night")
    hass.states.set("select.bedroom_cx_mode", "Night")
    return c


def _now(monkeypatch, hour, minute=0):
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda tz=None: datetime(2026, 10, 6, hour, minute, tzinfo=UTC))


def test_today_times_and_next_event(coord, monkeypatch):
    _now(monkeypatch, 12)
    coord._plan_schedule("time")
    state = coord.schedule_state()
    assert state["opening"] == datetime(2026, 10, 6, 7, 30, tzinfo=UTC)
    assert state["closing"] == datetime(2026, 10, 6, 20, 30, tzinfo=UTC)
    assert state["next_change"] == state["closing"]
    assert coord.timers[-1][1] == state["closing"]


def test_after_closing_the_timer_waits_for_midnight(coord, monkeypatch):
    _now(monkeypatch, 22)
    coord._plan_schedule("time")
    assert coord.timers[-1][1] == datetime(2026, 10, 7, 0, 0, tzinfo=UTC)
    assert coord.schedule_state()["next_change"] == datetime(2026, 10, 7, 7, 30, tzinfo=UTC)


def test_no_schedule_no_timer(coord, monkeypatch):
    coord._entry.options[OPT_CONFIG][SECTION_SCHEDULE] = {}
    coord._plan_schedule("time")
    assert coord.schedule_state() is None and coord.timers == []


def test_run_applies_each_covers_mode(coord):
    asyncio.run(coord._run_schedule("morning", datetime(2026, 10, 6).date()))
    # Living room has a morning mode; the bedroom has none.
    assert coord.hass.services.calls == [
        ("select", "select_option", {"entity_id": "select.living_room_cx_mode", "option": "Day"}),
    ]
    assert coord._schedule_last["morning"] == "2026-10-06"


def test_run_skips_a_cover_already_in_the_mode(coord):
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, 6).date()))
    assert coord.hass.services.calls == []   # both are already in Night


def test_first_start_catches_nothing_up(coord, monkeypatch):
    _now(monkeypatch, 22)
    coord._plan_schedule("time", catch_up=True)
    assert coord.hass.tasks == []
    assert coord._schedule_last == {"morning": "2026-10-06", "evening": "2026-10-06"}


def test_restart_after_a_missed_closing_catches_it_up(coord, monkeypatch):
    _now(monkeypatch, 22)
    coord._schedule_last = {"morning": "2026-10-06", "evening": "2026-10-05"}
    coord.hass.states.set("select.living_room_cx_mode", "Day")
    coord._plan_schedule("time", catch_up=True)
    assert len(coord.hass.tasks) == 1
    asyncio.run(coord.hass.tasks[0])
    assert coord.hass.services.calls[-1][2] == {"entity_id": "select.living_room_cx_mode", "option": "Night"}


def test_preview_returns_the_year(coord, monkeypatch):
    _now(monkeypatch, 12)
    preview = coord.schedule_preview("evening", {"type": "curve", "max": "21:00", "min": "19:00"})
    assert preview["error"] is None and len(preview["points"]) == DAYS
    assert len(preview["sun"]) == DAYS and preview["today"] == 279


# ── WebSocket validation ──────────────────────────────────────────────────────

@pytest.fixture
def ws_hass(hass, monkeypatch):
    sections = {
        SECTION_MODE: [{"name": "Day"}, {"name": "Night"}, {"name": "Manual", "duration": 60}],
        SECTION_COVER: [{"entity_id": LIVING, "modes": {"Day": {}, "Night": {}, "Manual": {}},
                         "schedule": {"morning": "Day", "evening": "Night"}}],
    }
    monkeypatch.setattr(ws, "_sections", lambda h: sections)
    return hass


def test_cover_schedule_drops_an_unlinked_mode(ws_hass):
    item = {"modes": {"Day": {}}, "schedule": {"morning": "Day", "evening": "Night"}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) is None
    assert item["schedule"] == {"morning": "Day", "evening": None}


def test_cover_schedule_refuses_a_timed_mode(ws_hass):
    item = {"modes": {"Manual": {}}, "schedule": {"morning": "Manual"}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) == "schedule_mode_timed:Manual"


def test_a_scheduled_mode_cannot_get_a_duration(ws_hass):
    old = [{"name": "Day"}, {"name": "Night"}]
    new = [{"name": "Day"}, {"name": "Night", "duration": 30}]
    assert ws._scheduled_mode_timed(ws_hass, new, old) == "schedule_mode_timed:Night"
    assert ws._scheduled_mode_timed(ws_hass, [{"name": "Day"}, {"name": "Night"}], old) is None


# ── Scheduled positions ───────────────────────────────────────────────────────

def _queued(c):
    items = []
    while not c._cover_queue.empty():
        items.append(c._cover_queue.get_nowait())
    return items


def _evening_position(coord, force, lock="off"):
    profile = coord.hass.data[DOMAIN][DATA_COVER_PROFILES][LIVING]
    profile[CONF_SCHEDULE] = {"morning": None, "evening": {"position": 0, "force": force}}
    coord.hass.data[DOMAIN][DATA_COVER_PROFILES][BEDROOM][CONF_SCHEDULE] = {"morning": None, "evening": None}
    coord.hass.states.set("switch.living_room_cx_lock", lock)
    return profile


def test_a_scheduled_position_moves_a_free_cover_and_keeps_its_mode(coord):
    _evening_position(coord, force=False)
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, 6).date()))
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 0})]
    assert coord.hass.services.calls == []   # no select_option: the mode stays
    assert coord._get_memory(LIVING) is None


def test_a_locked_cover_keeps_the_scheduled_position_in_memory(coord):
    _evening_position(coord, force=False, lock="on")
    coord.hass.data[DOMAIN][DATA_MEMORY][LIVING] = 80
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, 6).date()))
    assert _queued(coord) == []
    assert coord._get_memory(LIVING) == 0


def test_a_forced_position_moves_a_locked_cover_and_updates_its_memory(coord):
    _evening_position(coord, force=True, lock="on")
    coord.hass.data[DOMAIN][DATA_MEMORY][LIVING] = 80
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, 6).date()))
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 0})]
    # Leaving the locked mode must not reopen it to 80 %.
    assert coord._get_memory(LIVING) == 0


def test_a_forced_position_passes_the_inhibition_not_the_window(coord):
    profile = _evening_position(coord, force=True, lock="on")
    profile["inhibition"] = ["input_boolean.guest"]
    profile["exclusion"] = ["binary_sensor.window"]
    coord.hass.states.set("input_boolean.guest", "on")
    coord.hass.states.set("binary_sensor.window", "off")
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, 6).date()))
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 0})]
    coord.hass.states.set("binary_sensor.window", "on")
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, 7).date()))
    assert _queued(coord) == []
    # Waits for the window, then moves even though the cover is still locked.
    assert coord._exclusion_pending[LIVING] == (0, False, True)


def test_cover_schedule_keeps_a_position(ws_hass):
    item = {"modes": {"Night": {}}, "schedule": {"morning": {"position": 100, "force": True}, "evening": "Night"}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) is None
    assert item["schedule"] == {"morning": {"position": 100, "force": True}, "evening": "Night"}


@pytest.mark.parametrize("position", [101, -1, "50", None, True, 12.5])
def test_cover_schedule_refuses_a_position_it_cannot_read(ws_hass, position):
    item = {"modes": {}, "schedule": {"evening": {"position": position}}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) == f"schedule_position_invalid:{LIVING}"
