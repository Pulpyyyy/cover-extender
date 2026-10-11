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
    monkeypatch.setattr(c, "_sun_year", lambda kind, ref, year: sun)
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
    assert preview["suns"] == {"horizon": None, "civil": None, "nautical": None, "astronomical": None}


def test_preview_refuses_a_sun_event_that_does_not_happen(coord, monkeypatch):
    _now(monkeypatch, 12)
    sun = coord._sun_year("evening", "horizon", 2026)
    monkeypatch.setattr(coord, "_sun_year", lambda kind, ref, year: None if ref == "astronomical" else sun)
    cfg = {"type": "curve", "max": "21:00", "min": "19:00", "sun": "astronomical"}
    preview = coord.schedule_preview("evening", cfg)
    assert preview["error"] == "schedule_no_sun" and preview["suns"]["astronomical"] == "schedule_no_sun"
    assert preview["suns"]["civil"] is None
    # And the schedule does not run on it.
    assert coord._schedule_curve("evening", cfg, 2026) is None


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


# ── Scheduled positions read from an entity ───────────────────────────────────

SOURCE = "sensor.position_matin_amis"


def _evening_entity(coord, force=False, lock="off", source=SOURCE):
    profile = _evening_position(coord, force, lock)
    profile[CONF_SCHEDULE]["evening"] = {"position": {"type": "entity", "value": source}, "force": force}
    return profile


def _run_evening(coord, day=6):
    asyncio.run(coord._run_schedule("evening", datetime(2026, 10, day).date()))


def test_an_entity_position_moves_a_free_cover_to_its_value(coord):
    _evening_entity(coord)
    coord.hass.states.set(SOURCE, "100")
    _run_evening(coord)
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 100})]
    assert coord.hass.services.calls == []


def test_an_entity_position_is_rounded(coord):
    _evening_entity(coord)
    coord.hass.states.set(SOURCE, "49.5")
    _run_evening(coord)
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 50})]


def test_an_entity_position_is_read_when_the_schedule_runs(coord):
    _evening_entity(coord)
    coord.hass.states.set(SOURCE, "0")
    _run_evening(coord, 6)
    coord.hass.states.set(SOURCE, "100")
    _run_evening(coord, 7)
    assert [d["position"] for _s, d in _queued(coord)] == [0, 100]


def test_a_locked_cover_keeps_the_entity_position_in_memory(coord):
    _evening_entity(coord, lock="on")
    coord.hass.data[DOMAIN][DATA_MEMORY][LIVING] = 80
    coord.hass.states.set(SOURCE, "0")
    _run_evening(coord)
    assert _queued(coord) == []
    assert coord._get_memory(LIVING) == 0


def test_a_forced_entity_position_moves_a_locked_cover_and_updates_its_memory(coord):
    _evening_entity(coord, force=True, lock="on")
    coord.hass.data[DOMAIN][DATA_MEMORY][LIVING] = 80
    coord.hass.states.set(SOURCE, "0")
    _run_evening(coord)
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 0})]
    assert coord._get_memory(LIVING) == 0


def test_an_entity_position_waits_for_the_window_then_applies(coord):
    profile = _evening_entity(coord)
    profile["exclusion"] = ["binary_sensor.window"]
    coord.hass.states.set("binary_sensor.window", "on")
    coord.hass.states.set(SOURCE, "100")
    _run_evening(coord)
    assert _queued(coord) == []
    assert coord._exclusion_pending[LIVING][0] == 100
    # The value read when the schedule ran is the one applied, not a later one.
    coord.hass.states.set(SOURCE, "0")
    coord.hass.states.set("binary_sensor.window", "off")
    asyncio.run(coord._resume_after_exclusion(LIVING))
    assert _queued(coord) == [("set_cover_position", {"entity_id": LIVING, "position": 100})]


@pytest.mark.parametrize("state", [None, "unavailable", "unknown", "open", "", "nan", "101", "-1"])
def test_an_unreadable_entity_leaves_the_cover_alone(coord, caplog, state):
    _evening_entity(coord)
    bedroom = coord.hass.data[DOMAIN][DATA_COVER_PROFILES][BEDROOM]
    bedroom[CONF_SCHEDULE] = {"morning": None, "evening": {"position": 0, "force": False}}
    if state is not None:
        coord.hass.states.set(SOURCE, state)
    with caplog.at_level("WARNING"):
        _run_evening(coord)
    # The other covers run, this one does not move, and the log says why.
    assert _queued(coord) == [("set_cover_position", {"entity_id": BEDROOM, "position": 0})]
    assert coord._get_memory(LIVING) is None and LIVING not in coord._exclusion_pending
    warning = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warning) == 1 and LIVING in warning[0] and SOURCE in warning[0]
    if state is not None:
        assert repr(state) in warning[0]
    # The schedule ran all the same: nothing to catch up at the next start.
    assert coord._schedule_last["evening"] == "2026-10-06"


def test_cover_schedule_keeps_an_entity_position(ws_hass):
    action = {"position": {"type": "entity", "value": SOURCE}, "force": False}
    item = {"modes": {"Night": {}}, "schedule": {"morning": action, "evening": "Night"}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) is None
    assert item["schedule"] == {"morning": action, "evening": "Night"}


@pytest.mark.parametrize("value", ["", None])
def test_cover_schedule_wants_the_entity(ws_hass, value):
    item = {"modes": {}, "schedule": {"morning": {"position": {"type": "entity", "value": value}}}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) == f"schedule_entity_required:{LIVING}"


def test_cover_schedule_refuses_an_entity_that_is_not_a_number(ws_hass):
    item = {"modes": {}, "schedule": {"morning": {"position": {"type": "entity", "value": "light.kitchen"}}}}
    assert ws._validate_cover_schedule(ws_hass, item, LIVING) == f"schedule_position_invalid:{LIVING}"


def test_a_mode_rename_leaves_an_entity_position_alone(ws_hass, monkeypatch):
    action = {"position": {"type": "entity", "value": SOURCE}, "force": True}
    covers = [{"entity_id": LIVING, "modes": {"Night": {}}, "schedule": {"morning": action, "evening": "Night"}}]
    monkeypatch.setattr(ws, "_items", lambda h, section: covers)
    out = ws._renamed_covers(ws_hass, "mode", [{"name": "Day"}, {"name": "Night"}], [{"name": "Day"}, {"name": "Nuit"}])
    assert out[0]["schedule"] == {"morning": action, "evening": "Nuit"}


def test_an_entity_position_survives_a_save_and_a_reload(hass):
    """config/save, then what config/get returns and what the coordinator runs."""
    from custom_components.cover_extender.const import CONF_SCHEDULE as SCHED
    from custom_components.cover_extender.schemas import build_profiles_from_options

    entry = types.SimpleNamespace(options={OPT_CONFIG: {
        SECTION_MODE: [{"name": "Day"}, {"name": "Night"}],
        SECTION_COVER: [{"entity_id": LIVING, "modes": {"Day": {"type": "fixed", "value": 100}}}],
    }})

    def update(e, options):
        e.options = options

    hass.config_entries = types.SimpleNamespace(async_entries=lambda domain: [entry], async_update_entry=update)
    sent = []
    connection = types.SimpleNamespace(
        send_result=lambda i, r: sent.append(("ok", r)), send_error=lambda i, c, m: sent.append(("error", m)),
    )
    action = {"position": {"type": "entity", "value": SOURCE}, "force": True}
    ws._save_schedule(hass, connection, {"id": 1, "data": {
        "house": dict(HOUSE), "covers": {LIVING: {"morning": action, "evening": "Day"}},
    }})
    assert sent == [("ok", {"saved": True})]
    assert ws._items(hass, SECTION_COVER)[0]["schedule"] == {"morning": action, "evening": "Day"}
    profiles = build_profiles_from_options(entry, hass)[0]
    assert profiles[LIVING][SCHED] == {"morning": action, "evening": "Day"}
