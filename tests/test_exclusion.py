"""Tests for the exclusion entities (e.g. an open window) in the coordinator.

An active exclusion must block every move Cover Extender issues: autonomous
shading, solar gain and the lock-aware services. Like test_external_attrs.py,
this module needs the real Home Assistant package and is skipped locally.
"""
from __future__ import annotations

import asyncio
import types

import pytest

# Real HA only: the stub conftest never provides homeassistant.config_entries.
pytest.importorskip("homeassistant.config_entries")

from custom_components.cover_extender import coordinator as coord_mod
from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_MODES,
    DATA_SOLAR_GAIN,
    CONF_EXCLUSION,
    CONF_FACADE,
    CONF_MODES,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
)

from conftest import FakeState

COVER = "cover.office"
WINDOW = "binary_sensor.office_window"


class FakeBus:
    def __init__(self):
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.fired.append((event_type, data))


class FakeServices:
    """Switch calls land in the state machine, like the real switch platform."""

    def __init__(self, hass):
        self._hass = hass

    async def async_call(self, domain: str, service: str, data: dict) -> None:
        self._hass.states.set(data["entity_id"], "on" if service == "turn_on" else "off")


class FakeStore:
    def async_delay_save(self, *_a, **_k) -> None:
        pass


@pytest.fixture
def coord(hass, monkeypatch):
    """A coordinator with one south-facing cover, shade and solar gain enabled."""
    monkeypatch.setattr(coord_mod.er, "async_get", lambda h: h.entity_registry)
    monkeypatch.setattr(coord_mod, "Store", lambda *a, **k: FakeStore())
    hass.bus = FakeBus()
    hass.services = FakeServices(hass)
    hass.tasks = []
    hass.async_create_task = hass.tasks.append
    c = CoverExtenderCoordinator(hass, types.SimpleNamespace())
    hass.data[DOMAIN] = {
        DATA_COVER_PROFILES: {
            COVER: {
                CONF_FACADE: "South",
                CONF_MODES: {"Day": 100, "Night": 0},
                CONF_EXCLUSION: [WINDOW],
                CONF_SHADING: {"enable": True},
                CONF_SOLAR_GAIN: {"enable": True, "position_solar": 100, "position_cold": 0},
            }
        },
        DATA_FACADES: {"South": {"azimuth": 180}},
        DATA_MODES: {"Day": {"lock": False}, "Night": {"lock": True}},
        DATA_SOLAR_GAIN: {},
        DATA_MEMORY: {},
    }
    # Sun straight in front of the facade: shading computes a real move.
    hass.states.set("sun.sun", "above_horizon", {"azimuth": 180, "elevation": 30})
    hass.states.set(COVER, "open", {"current_position": 100})
    hass.states.set("switch.office_auto_shade", "on")
    hass.states.set("switch.office_auto_solar_gain", "on")
    hass.states.set("switch.office_lock", "off")
    return c


def _queued(c: CoverExtenderCoordinator) -> list[tuple[str, dict]]:
    items = []
    while not c._cover_queue.empty():
        items.append(c._cover_queue.get_nowait())
    return items


@pytest.mark.parametrize("window, expected", [("on", True), ("off", False)])
def test_is_excluded(coord, hass, window, expected):
    hass.states.set(WINDOW, window)
    assert coord._is_excluded(COVER) is expected


def test_is_excluded_unknown_cover(coord):
    assert coord._is_excluded("cover.unknown") is False


def test_shade_moves_without_exclusion(coord, hass):
    hass.states.set(WINDOW, "off")
    coord._apply_shade(COVER, coord._profiles[COVER])
    assert [s for s, _ in _queued(coord)] == ["set_cover_position"]


def test_shade_blocked_by_exclusion(coord, hass):
    hass.states.set(WINDOW, "on")
    coord._apply_shade(COVER, coord._profiles[COVER])
    assert _queued(coord) == []
    assert hass.bus.fired == []


def test_solar_gain_blocked_by_exclusion(coord, hass):
    hass.states.set(WINDOW, "on")
    coord._apply_solar_gain(COVER, coord._profiles[COVER])
    assert _queued(coord) == []


def test_solar_gain_moves_without_exclusion(coord, hass):
    hass.states.set(WINDOW, "off")
    coord._apply_solar_gain(COVER, coord._profiles[COVER])
    assert _queued(coord) == [
        ("set_cover_position", {"entity_id": COVER, "position": 100})
    ]


def test_service_position_memorized_when_excluded(coord, hass):
    hass.states.set(WINDOW, "on")
    asyncio.run(coord._set_cover_position_impl([COVER], 40))
    assert _queued(coord) == []
    assert coord._get_memory(COVER) == 40


def test_service_position_moves_without_exclusion(coord, hass):
    hass.states.set(WINDOW, "off")
    asyncio.run(coord._set_cover_position_impl([COVER], 40))
    assert _queued(coord) == [
        ("set_cover_position", {"entity_id": COVER, "position": 40})
    ]
    assert coord._get_memory(COVER) is None


# ── Resuming when the exclusion clears ────────────────────────────────────────

def _window_event(old: str, new: str):
    return types.SimpleNamespace(data={
        "entity_id": WINDOW,
        "old_state": FakeState(old),
        "new_state": FakeState(new),
    })


def _no_shade(coord):
    """Keep shading and solar gain out of the resume tests."""
    coord._profiles[COVER][CONF_SHADING] = {"enable": False}
    coord._profiles[COVER][CONF_SOLAR_GAIN] = {"enable": False}


def test_action_applied_when_window_closes(coord, hass):
    _no_shade(coord)
    hass.states.set(WINDOW, "on")
    asyncio.run(coord._set_cover_position_impl([COVER], 40))
    hass.states.set(WINDOW, "off")
    asyncio.run(coord._resume_after_exclusion(COVER))
    assert _queued(coord) == [
        ("set_cover_position", {"entity_id": COVER, "position": 40})
    ]
    assert coord._get_memory(COVER) is None


def test_action_waits_for_unlock_if_locked_meanwhile(coord, hass):
    _no_shade(coord)
    hass.states.set(WINDOW, "on")
    asyncio.run(coord._set_cover_position_impl([COVER], 40))
    hass.states.set("switch.office_lock", "on")
    hass.states.set(WINDOW, "off")
    asyncio.run(coord._resume_after_exclusion(COVER))
    assert _queued(coord) == []
    assert coord._get_memory(COVER) == 40


def test_stale_memory_is_never_applied(coord, hass):
    """A memory left from an older locked period must not come back."""
    _no_shade(coord)
    asyncio.run(coord._set_memory(COVER, 70))
    asyncio.run(coord._resume_after_exclusion(COVER))
    assert _queued(coord) == []
    assert coord._get_memory(COVER) == 70


def test_locked_mode_position_applied_and_memory_kept(coord, hass):
    """Night (locked, 0 %) chosen with the window open: the cover closes when
    the window does, and the memory keeps the position from before Night."""
    _no_shade(coord)
    hass.states.set(WINDOW, "on")
    asyncio.run(coord._apply_mode_core(COVER, "Night", "Day"))
    assert _queued(coord) == []
    assert coord._get_memory(COVER) == 100
    hass.states.set(WINDOW, "off")
    asyncio.run(coord._resume_after_exclusion(COVER))
    assert _queued(coord) == [
        ("set_cover_position", {"entity_id": COVER, "position": 0})
    ]
    assert coord._get_memory(COVER) == 100


def test_new_mode_replaces_pending(coord, hass):
    _no_shade(coord)
    hass.states.set(WINDOW, "on")
    asyncio.run(coord._set_cover_position_impl([COVER], 40))
    asyncio.run(coord._apply_mode_core(COVER, "Night", "Day"))
    assert coord._exclusion_pending[COVER] == (0, False)


def test_shading_catches_up_when_window_closes(coord, hass):
    hass.states.set(WINDOW, "off")
    asyncio.run(coord._resume_after_exclusion(COVER))
    assert "set_cover_position" in [s for s, _ in _queued(coord)]


@pytest.mark.parametrize("old, new, other, scheduled", [
    ("on", "off", "off", True),    # last exclusion cleared
    ("on", "off", "on", False),    # another exclusion still on
    ("off", "on", "off", False),   # window opening
    ("on", "on", "off", False),    # attribute-only change
])
def test_exclusion_listener(coord, hass, old, new, other, scheduled):
    other_id = "binary_sensor.office_door"
    coord._profiles[COVER][CONF_EXCLUSION] = [WINDOW, other_id]
    coord._exclusion_to_covers = {WINDOW: [COVER], other_id: [COVER]}
    hass.states.set(WINDOW, new)
    hass.states.set(other_id, other)
    coord._handle_exclusion_change(_window_event(old, new))
    assert (len(hass.tasks) == 1) is scheduled
    for task in hass.tasks:
        task.close()
