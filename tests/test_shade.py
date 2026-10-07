"""Tests for the pure solar-geometry functions (shade.py)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from custom_components.cover_extender.const import DOMAIN, DATA_FACADES
from custom_components.cover_extender.shade import (
    compute_facade_lit,
    compute_shade_sync,
    compute_sun_facing,
    cos_incidence,
    sun_height,
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

def _shade_cfg(angles: dict | None = None, **overrides) -> dict:
    shade = {
        "distance": 1.0,
        "max_height": 2.0,
        "min_height": 0.0,
        "max_elevation": 90,
        "min_elevation": 5,
        "minimum_position": 10,
        "default_position": 100,
        "change_threshold": 5,
        "time_out": 2,
    }
    shade.update(overrides)
    return {"facade": "south", "shade": shade, **(angles or {})}


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


# ── the sector: the cover's own left / right angles ──────────────────────────

def test_shade_sun_beyond_left_angle_takes_default(hass):
    # Sun 70° to the left of a south facade (azimuth 110): outside a 60° left angle.
    _setup(hass)
    _set_sun(hass, azimuth=110, elevation=20)
    position, should_update = compute_shade_sync(
        hass, "cover.volet", _shade_cfg(angles={"angle_left": 60, "angle_right": 85}))
    assert position == 100
    assert should_update is True


def test_shade_sun_within_left_angle_is_computed(hass):
    # Same sun, left angle 85°: h = 1 / cos 70° * tan 20° = 1.064 m → 53 % of [0, 2] m.
    _setup(hass)
    _set_sun(hass, azimuth=110, elevation=20)
    position, _ = compute_shade_sync(
        hass, "cover.volet", _shade_cfg(angles={"angle_left": 85, "angle_right": 85}))
    assert position == 53


def test_shade_sector_is_asymmetric(hass):
    # Right angle 30°: a sun 40° to the right is outside, one 20° to the right inside.
    _setup(hass)
    cfg = _shade_cfg(angles={"angle_left": 85, "angle_right": 30})
    _set_sun(hass, azimuth=220, elevation=20)
    assert compute_shade_sync(hass, "cover.volet", cfg)[0] == 100
    _set_sun(hass, azimuth=200, elevation=20)
    # h = 1 / cos 20° * tan 20° = 0.387 m → 19 %
    assert compute_shade_sync(hass, "cover.volet", cfg)[0] == 19


def test_shade_sector_matches_sun_facing(hass):
    # Shading and the "sun facing" sensor answer the same question the same way.
    _setup(hass)
    cfg = _shade_cfg(angles={"angle_left": 45, "angle_right": 60})
    for azimuth in (130, 140, 180, 235, 245):
        _set_sun(hass, azimuth=azimuth, elevation=30)
        facing = compute_sun_facing(hass, cfg, FACADES)
        position, _ = compute_shade_sync(hass, "cover.volet", cfg)
        assert facing is (position != 100), azimuth


def test_shade_ignores_a_retired_aperture(hass):
    # An old "degrees" left in a stored configuration no longer narrows anything.
    _setup(hass)
    _set_sun(hass, azimuth=110, elevation=20)
    position, _ = compute_shade_sync(
        hass, "cover.volet", _shade_cfg(angles={"angle_left": 85, "angle_right": 85}, degrees=30))
    assert position == 53


def test_shade_below_min_elevation_takes_default(hass):
    _setup(hass)
    _set_sun(hass, azimuth=180, elevation=20)
    assert compute_shade_sync(hass, "cover.volet", _shade_cfg(min_elevation=30))[0] == 100


# ── sloped and flat windows ───────────────────────────────────────────────────

SLOPED = {
    **FACADES,
    "roof_south": {"azimuth": 180.0, "tilt": 30},
    "roof_north": {"azimuth": 0.0, "tilt": 30},
    "skylight": {"azimuth": 180.0, "tilt": 0},
}
WIDE = {"angle_left": 180, "angle_right": 180}


def _setup_sloped(hass) -> None:
    hass.data[DOMAIN] = {DATA_FACADES: SLOPED}


def _roof_cfg(facade: str, **overrides) -> dict:
    # The range runs to 180°: over the zenith, down to the roof.
    return {**_shade_cfg(WIDE, **{"max_elevation": 180, **overrides}), "facade": facade}


def test_sun_height_reads_over_the_zenith():
    assert sun_height(60, 10, 30) == 60       # in front of a roof
    assert sun_height(60, 170, 30) == 120     # behind it, read over the zenith
    assert sun_height(60, 170, 90) == 60      # a wall has no "behind" to read
    assert sun_height(60, 170, 0) == 60       # nor has a flat window


def test_wall_incidence_is_the_familiar_one():
    # On a wall, cos(incidence) = cos(elevation) * cos(offset).
    assert math.isclose(cos_incidence(40, 25, 90), math.cos(math.radians(40)) * math.cos(math.radians(25)))


def test_wall_ignores_the_sky_behind_it_whatever_the_angles(hass):
    # Angles opened to 180° (a template shared with a roof) never let a wall
    # see a sun behind it: the glass test keeps it out.
    _set_sun(hass, azimuth=0, elevation=30)
    assert compute_facade_lit(hass, "south", SLOPED, 180, 180) is False


def test_roof_sees_a_high_sun_behind_it(hass):
    # North roof at 30°, sun due south 45° high: above the roof's plane.
    _set_sun(hass, azimuth=180, elevation=45)
    assert compute_facade_lit(hass, "roof_north", SLOPED, 180, 180) is True
    # The same sun 20° high is below the plane: the roof hides it.
    _set_sun(hass, azimuth=180, elevation=20)
    assert compute_facade_lit(hass, "roof_north", SLOPED, 180, 180) is False


def test_roof_behind_still_needs_the_sector(hass):
    # The angles stay a mask: at 85° a sun behind is outside them.
    _set_sun(hass, azimuth=180, elevation=45)
    assert compute_facade_lit(hass, "roof_north", SLOPED, 85, 85) is False


def test_skylight_sees_the_whole_sky(hass):
    for azimuth in (0, 90, 180, 270):
        _set_sun(hass, azimuth=azimuth, elevation=10)
        assert compute_facade_lit(hass, "skylight", SLOPED, 180, 180) is True


def test_shade_on_a_roof_facing_the_sun(hass):
    # South roof at 30°, sun due south 45° high: cos i = sin 45 cos 30 + cos 45 sin 30
    # = 0.966, open length 1 * sin 45 / 0.966 = 0.732 m → 37 % of [0, 2] m.
    _setup_sloped(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    assert compute_shade_sync(hass, "cover.velux", _roof_cfg("roof_south"))[0] == 37


def test_shade_on_a_roof_with_the_sun_behind(hass):
    # North roof at 30°, sun due south 45° high: cos i = 0.259, open length
    # 0.5 * sin 45 / 0.259 = 1.366 m → 68 %. Its height on the range is 135°.
    _setup_sloped(hass)
    _set_sun(hass, azimuth=180, elevation=45)
    assert compute_shade_sync(hass, "cover.velux", _roof_cfg("roof_north", distance=0.5))[0] == 68
    # A range stopping at 120° (60° behind) leaves that sun out.
    cfg = _roof_cfg("roof_north", distance=0.5, max_elevation=120)
    assert compute_shade_sync(hass, "cover.velux", cfg)[0] == 100


def test_shade_on_a_roof_ignores_a_sun_below_its_plane(hass):
    _setup_sloped(hass)
    _set_sun(hass, azimuth=180, elevation=20)
    assert compute_shade_sync(hass, "cover.velux", _roof_cfg("roof_north", distance=0.5))[0] == 100


def test_shade_on_a_skylight_takes_its_sun_position(hass):
    _setup_sloped(hass)
    _set_sun(hass, azimuth=90, elevation=30)
    cfg = _roof_cfg("skylight", sun_position=40)
    assert compute_shade_sync(hass, "cover.skylight", cfg)[0] == 40
    # Under the minimum height, the default position as anywhere else.
    _set_sun(hass, azimuth=90, elevation=4)
    assert compute_shade_sync(hass, "cover.skylight", cfg)[0] == 100


def test_shade_sector_matches_sun_facing_on_a_roof(hass):
    _setup_sloped(hass)
    cfg = _roof_cfg("roof_north", distance=0.5)
    for azimuth, elevation in ((180, 45), (180, 20), (90, 15), (0, 30), (150, 40)):
        _set_sun(hass, azimuth=azimuth, elevation=elevation)
        facing = compute_sun_facing(hass, cfg, SLOPED)
        position, _ = compute_shade_sync(hass, "cover.velux", cfg)
        assert facing is (position != 100), (azimuth, elevation)
