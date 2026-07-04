"""Tests for the pure solar-geometry functions (shade.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.cover_extender.const import DOMAIN, DATA_FACADES
from custom_components.cover_extender.shade import (
    compute_facade_lit,
    compute_shade_sync,
    compute_sun_facing,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _set_sun(hass, azimuth: float, elevation: float) -> None:
    hass.states.set("sun.sun", "above_horizon", {"azimuth": azimuth, "elevation": elevation})


FACADES = {"south": {"azimuth": 180.0}, "north": {"azimuth": 0.0}}


# ── compute_facade_lit ────────────────────────────────────────────────────────

def test_facade_lit_no_sun_entity(hass):
    assert compute_facade_lit(hass, "south", FACADES) is None


def test_facade_lit_below_min_elevation(hass):
    _set_sun(hass, azimuth=180, elevation=2.9)
    assert compute_facade_lit(hass, "south", FACADES) is False


def test_facade_lit_inside_window(hass):
    _set_sun(hass, azimuth=180, elevation=30)
    assert compute_facade_lit(hass, "south", FACADES) is True


def test_facade_lit_outside_window(hass):
    _set_sun(hass, azimuth=20, elevation=30)
    assert compute_facade_lit(hass, "south", FACADES, angle_left=45, angle_right=45) is False


def test_facade_lit_wraps_around_north(hass):
    # North facade (0°) with ±85° window → [275°, 85°], crossing 0/360
    _set_sun(hass, azimuth=350, elevation=30)
    assert compute_facade_lit(hass, "north", FACADES) is True
    _set_sun(hass, azimuth=180, elevation=30)
    assert compute_facade_lit(hass, "north", FACADES) is False


def test_facade_lit_unknown_facade_uses_default_azimuth(hass):
    # Unknown facade falls back to azimuth 180
    _set_sun(hass, azimuth=180, elevation=30)
    assert compute_facade_lit(hass, "missing", FACADES) is True


# ── compute_sun_facing ────────────────────────────────────────────────────────

def test_sun_facing_without_facade_is_none(hass):
    _set_sun(hass, azimuth=180, elevation=30)
    assert compute_sun_facing(hass, {}, FACADES) is None


def test_sun_facing_uses_per_cover_angles(hass):
    _set_sun(hass, azimuth=250, elevation=30)
    wide = {"facade": "south", "angle_left": 85, "angle_right": 85}
    narrow = {"facade": "south", "angle_left": 30, "angle_right": 30}
    assert compute_sun_facing(hass, wide, FACADES) is True
    assert compute_sun_facing(hass, narrow, FACADES) is False


# ── compute_shade_sync ────────────────────────────────────────────────────────

def _shade_cfg(**overrides) -> dict:
    shade = {
        "distance": 1.0,
        "max_height": 2.0,
        "min_height": 0.0,
        "degrees": 90,
        "max_elevation": 90,
        "min_elevation": 5,
        "minimum_position": 10,
        "default_position": 100,
        "change_threshold": 5,
        "time_out": 2,
    }
    shade.update(overrides)
    return {"facade": "south", "shade": shade}


def _setup(hass) -> None:
    hass.data[DOMAIN] = {DATA_FACADES: FACADES}


def test_shade_no_sun_returns_default(hass):
    _setup(hass)
    position, should_update = compute_shade_sync(hass, "cover.volet", _shade_cfg())
    assert position == 100
    assert should_update is False


def test_shade_sun_outside_fov_returns_default_position(hass):
    _setup(hass)
    _set_sun(hass, azimuth=0, elevation=45)  # opposite side of a south facade
    position, should_update = compute_shade_sync(hass, "cover.volet", _shade_cfg())
    assert position == 100
    assert should_update is True


def test_shade_geometry_45_degrees(hass):
    # gamma=0, alpha=45° → h = distance*tan(45°) = 1.0 m → 50 % of [0, 2] m
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    position, should_update = compute_shade_sync(hass, "cover.volet", _shade_cfg())
    assert position == 50
    assert should_update is True


def test_shade_clips_to_minimum_position(hass):
    # Very low sun → tiny height → clipped to minimum_position
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=6)
    position, _ = compute_shade_sync(hass, "cover.volet", _shade_cfg())
    assert position == 10


def test_shade_threshold_suppresses_move(hass):
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=45)  # computed 50 %
    hass.states.set("cover.volet", "open", {"current_position": 48})
    position, should_update = compute_shade_sync(hass, "cover.volet", _shade_cfg())
    assert position == 48
    assert should_update is False


def test_shade_current_position_none_does_not_crash(hass):
    # Some integrations report current_position: None while moving. Unknown
    # position is treated as already-in-place (diff 0) → no command issued.
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    hass.states.set("cover.volet", "open", {"current_position": None})
    position, should_update = compute_shade_sync(hass, "cover.volet", _shade_cfg())
    assert position == 50
    assert should_update is False


def test_shade_time_out_throttles_recent_move(hass):
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    hass.states.set("cover.volet", "open", {"current_position": 0})
    position, should_update = compute_shade_sync(
        hass, "cover.volet", _shade_cfg(), last_move=_utcnow()
    )
    assert position == 50
    assert should_update is False


def test_shade_time_out_elapsed_allows_move(hass):
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    hass.states.set("cover.volet", "open", {"current_position": 0})
    position, should_update = compute_shade_sync(
        hass, "cover.volet", _shade_cfg(), last_move=_utcnow() - timedelta(minutes=10)
    )
    assert position == 50
    assert should_update is True


def test_shade_no_last_move_bypasses_throttle(hass):
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    hass.states.set("cover.volet", "open", {"current_position": 0})
    _, should_update = compute_shade_sync(hass, "cover.volet", _shade_cfg(), last_move=None)
    assert should_update is True


def test_shade_default_position_respects_min_height(hass):
    # default 50 % of [1.0, 2.0] m must map back to exactly 50 %
    _setup(hass)
    _set_sun(hass, azimuth=0, elevation=45)  # outside FOV → default position
    cfg = _shade_cfg(min_height=1.0, default_position=50)
    position, _ = compute_shade_sync(hass, "cover.volet", cfg)
    assert position == 50
