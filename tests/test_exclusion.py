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
    DATA_SOLAR_GAIN,
    CONF_EXCLUSION,
    CONF_FACADE,
    CONF_MODES,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
)

COVER = "cover.office"
WINDOW = "binary_sensor.office_window"


class FakeBus:
    def __init__(self):
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.fired.append((event_type, data))


class FakeStore:
    def async_delay_save(self, *_a, **_k) -> None:
        pass


@pytest.fixture
def coord(hass, monkeypatch):
    """A coordinator with one south-facing cover, shade and solar gain enabled."""
    monkeypatch.setattr(coord_mod.er, "async_get", lambda h: h.entity_registry)
    monkeypatch.setattr(coord_mod, "Store", lambda *a, **k: FakeStore())
    hass.bus = FakeBus()
    c = CoverExtenderCoordinator(hass, types.SimpleNamespace())
    hass.data[DOMAIN] = {
        DATA_COVER_PROFILES: {
            COVER: {
                CONF_FACADE: "South",
                CONF_MODES: {},
                CONF_EXCLUSION: [WINDOW],
                CONF_SHADING: {"enable": True},
                CONF_SOLAR_GAIN: {"enable": True, "position_solar": 100, "position_cold": 0},
            }
        },
        DATA_FACADES: {"South": {"azimuth": 180}},
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
