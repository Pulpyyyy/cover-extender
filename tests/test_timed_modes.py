"""Tests for timed modes.

A timed mode is a parenthesis over the cover's base mode, the last non-timed
mode it was put in. When the time is up the cover returns to that base mode,
or to the mode's fixed return mode (always non-timed). Another timed mode
chosen meanwhile replaces the parenthesis and keeps the base; a non-timed mode
closes it at once; the running timed mode chosen again extends it.
"""
from __future__ import annotations

import asyncio
import types
from datetime import timedelta

import pytest

from custom_components.cover_extender import coordinator as coord_mod
from custom_components.cover_extender.const import (
    CONF_MODES,
    DATA_COVER_PROFILES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_MODES,
    DATA_SOLAR_GAIN,
    DOMAIN,
)
from custom_components.cover_extender.coordinator import CoverExtenderCoordinator

COVER = "cover.office"
SELECT = "select.office_cx_mode"


class FakeBus:
    def __init__(self):
        self.fired = []

    def async_fire(self, event_type, data):
        self.fired.append((event_type, data))


class FakeServices:
    """select_option writes the option, switch calls write on/off."""

    def __init__(self, hass):
        self._hass = hass
        self.calls = []

    async def async_call(self, domain, service, data):
        self.calls.append((domain, service, data))
        if domain == "select":
            self._hass.states.set(data["entity_id"], data["option"])
        else:
            self._hass.states.set(data["entity_id"], "on" if service == "turn_on" else "off")


class FakeStore:
    def __init__(self):
        self.saved = None

    def async_delay_save(self, func, *_a):
        self.saved = func()


@pytest.fixture
def coord(hass, monkeypatch):
    monkeypatch.setattr(coord_mod.er, "async_get", lambda h: h.entity_registry)
    monkeypatch.setattr(coord_mod, "Store", lambda *a, **k: FakeStore())
    scheduled = []
    monkeypatch.setattr(
        coord_mod, "async_track_point_in_utc_time",
        lambda h, action, point: scheduled.append((action, point)) or (lambda: None),
    )
    monkeypatch.setattr(coord_mod, "async_dispatcher_send", lambda *a: None)
    hass.bus = FakeBus()
    hass.services = FakeServices(hass)
    hass.tasks = []
    hass.async_create_task = hass.tasks.append
    c = CoverExtenderCoordinator(hass, types.SimpleNamespace())
    c.scheduled = scheduled
    hass.data[DOMAIN] = {
        DATA_COVER_PROFILES: {COVER: {CONF_MODES: {
            "Day": None, "Night": None, "Manual": None, "Guest": None, "Pause": None,
        }}},
        DATA_FACADES: {},
        DATA_MODES: {
            "Day": {}, "Night": {},
            "Manual": {"duration": 60},
            "Guest": {"duration": 720},
            "Pause": {"duration": 30, "return_mode": "Night"},   # fixed return
        },
        DATA_SOLAR_GAIN: {},
        DATA_MEMORY: {},
    }
    hass.states.set(COVER, "open", {"current_position": 100})
    hass.states.set(SELECT, "Day")
    return c


def _choose(coord, hass, mode):
    """A mode change as it happens: the selector shows it, the coordinator applies it."""
    from_mode = hass.states.get(SELECT).state
    hass.states.set(SELECT, mode)
    asyncio.run(coord._apply_mode_core(COVER, mode, from_mode))


def _time_is_up(coord, hass):
    """The countdown ends, and the selector change it makes reaches the coordinator."""
    before = hass.states.get(SELECT).state
    asyncio.run(coord.async_end_timed_mode(COVER))
    after = hass.states.get(SELECT).state
    if after != before:
        asyncio.run(coord._apply_mode_core(COVER, after, before))


def test_timed_mode_returns_to_the_base_mode(coord, hass):
    before = coord_mod.dt_util.utcnow()
    _choose(coord, hass, "Manual")
    info = coord.timed_mode_info(COVER)
    assert info["return_mode"] == "Day"
    assert timedelta(minutes=59) < info["until"] - before <= timedelta(minutes=61)
    assert coord.scheduled[-1][1] == info["until"]
    assert coord._timer_store.saved  # persisted
    _time_is_up(coord, hass)
    assert hass.states.get(SELECT).state == "Day"
    ended = [data for kind, data in hass.bus.fired if kind == "cover_extender_timed_mode_ended"]
    assert ended == [{"entity_id": COVER, "mode": "Manual", "return_mode": "Day"}]
    assert coord.timed_mode_info(COVER) is None


def test_another_timed_mode_keeps_the_base_mode(coord, hass):
    # Day, then Manual, then Guest before Manual ends: Guest returns to Day.
    _choose(coord, hass, "Manual")
    _choose(coord, hass, "Guest")
    assert coord.timed_mode_info(COVER)["return_mode"] == "Day"
    _time_is_up(coord, hass)
    assert hass.states.get(SELECT).state == "Day"
    assert coord.timed_mode_info(COVER) is None


def test_a_non_timed_mode_closes_the_parenthesis_and_becomes_the_base(coord, hass):
    _choose(coord, hass, "Manual")
    _choose(coord, hass, "Night")
    assert coord.timed_mode_info(COVER) is None
    assert coord._timer_store.saved == {}
    _choose(coord, hass, "Manual")
    assert coord.timed_mode_info(COVER)["return_mode"] == "Night"


def test_fixed_return_mode_wins_over_the_base_mode(coord, hass):
    _choose(coord, hass, "Pause")
    assert coord.timed_mode_info(COVER)["return_mode"] == "Night"
    _time_is_up(coord, hass)
    assert hass.states.get(SELECT).state == "Night"


def test_fixed_return_not_linked_falls_back_to_the_base_mode(coord, hass):
    del coord._profiles[COVER][CONF_MODES]["Night"]
    _choose(coord, hass, "Pause")
    _time_is_up(coord, hass)
    assert hass.states.get(SELECT).state == "Day"


def test_base_mode_gone_the_cover_stays(coord, hass):
    _choose(coord, hass, "Manual")
    del coord._profiles[COVER][CONF_MODES]["Day"]
    asyncio.run(coord.async_end_timed_mode(COVER))
    assert hass.states.get(SELECT).state == "Manual"
    assert coord.timed_mode_info(COVER) is None


def test_reselecting_extends(coord, hass):
    _choose(coord, hass, "Manual")
    first = coord.timed_mode_info(COVER)["until"]
    coord._timers[COVER]["until"] = first - timedelta(minutes=30)   # time passes
    coord.extend_timed_mode(COVER, "Manual")
    info = coord.timed_mode_info(COVER)
    assert info["until"] >= first and info["return_mode"] == "Day"


def test_no_countdown_without_a_mode_to_go_back_to(coord, hass):
    asyncio.run(coord._apply_mode_core(COVER, "Manual", None))
    assert coord.timed_mode_info(COVER) is None


@pytest.mark.parametrize("sequence", [
    ["Manual", "Guest", "Manual", "Guest"],
    ["Guest", "Pause", "Manual"],
    ["Pause", "Manual", "Night", "Guest", "Pause"],
])
def test_every_ending_lands_on_a_non_timed_mode(coord, hass, sequence):
    """Whatever was chosen before, one ending is enough: no chain of returns."""
    for mode in sequence:
        _choose(coord, hass, mode)
    _time_is_up(coord, hass)
    assert hass.states.get(SELECT).state in ("Day", "Night")
    assert coord.timed_mode_info(COVER) is None


def test_restore_after_restart(coord, hass):
    _choose(coord, hass, "Guest")
    saved = coord._timer_store.saved
    coord._timers.clear()
    coord._stored_timers = saved
    coord._restore_timers()
    assert coord.timed_mode_info(COVER)["return_mode"] == "Day"


def test_restore_drops_a_countdown_whose_mode_changed(coord, hass):
    _choose(coord, hass, "Guest")
    saved = coord._timer_store.saved
    coord._timers.clear()
    hass.states.set(SELECT, "Night")
    coord._stored_timers = saved
    coord._restore_timers()
    assert coord.timed_mode_info(COVER) is None


@pytest.mark.parametrize("target", ["Night", "Day"])
def test_forced_switch_to_a_non_timed_mode_ends_the_countdown(coord, hass, target):
    """apply_mode with force: true, to another mode or to the base mode itself."""
    _choose(coord, hass, "Manual")

    async def covers(_call):
        return [COVER]

    coord._extract_cover_ids = covers
    call = types.SimpleNamespace(data={"mode": target, "force": True})
    asyncio.run(coord.service_apply_mode(call))
    # The selector change reaches the coordinator.
    asyncio.run(coord._apply_mode_core(COVER, target, "Manual"))
    assert hass.states.get(SELECT).state == target
    assert coord.timed_mode_info(COVER) is None
    assert coord._timer_store.saved == {}


def test_forced_same_timed_mode_extends(coord, hass):
    _choose(coord, hass, "Manual")
    coord._timers[COVER]["until"] -= timedelta(minutes=30)   # time passes
    before = coord_mod.dt_util.utcnow()

    async def covers(_call):
        return [COVER]

    coord._extract_cover_ids = covers
    asyncio.run(coord.service_apply_mode(types.SimpleNamespace(data={"mode": "Manual", "force": True})))
    info = coord.timed_mode_info(COVER)
    assert info["until"] - before > timedelta(minutes=59)
    assert info["return_mode"] == "Day"


def test_a_fixed_return_with_a_duration_is_never_followed(coord, hass):
    """Should a configuration slip past the validation (Pause returning to a
    timed mode), the countdown still ends on the base mode: no loop."""
    coord._modes_list["Pause"]["return_mode"] = "Guest"
    _choose(coord, hass, "Pause")
    assert coord.timed_mode_info(COVER)["return_mode"] == "Day"
    _time_is_up(coord, hass)
    assert hass.states.get(SELECT).state == "Day"
    assert coord.timed_mode_info(COVER) is None
