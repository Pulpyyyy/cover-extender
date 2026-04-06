"""Tests for solar geometry helpers: compute_sun_facing and compute_shade_sync."""
from __future__ import annotations

import math
import pytest

from custom_components.cover_extender.shade import compute_sun_facing, compute_shade_sync
from .conftest import make_hass, BASE_SHADE_CFG


# ════════════════════════════════════════════════════════════════════════════
# compute_sun_facing
# ════════════════════════════════════════════════════════════════════════════

class TestComputeSunFacing:
    """Tests for compute_sun_facing."""

    FACADES = {"sud": {"azimuth": 180.0}}

    def cfg(self, facade="sud", angle_left=85.0, angle_right=85.0):
        return {"facade": facade, "angle_left": angle_left, "angle_right": angle_right}

    # ── Prerequisites ─────────────────────────────────────────────────────

    def test_no_facade_returns_none(self):
        """A cover without facade config always returns None."""
        assert compute_sun_facing(make_hass(), {}, self.FACADES) is None

    def test_sun_unavailable_returns_none(self):
        """sun.sun state missing → None (can't determine facing)."""
        assert compute_sun_facing(make_hass(sun_ok=False), self.cfg(), self.FACADES) is None

    def test_elevation_below_3_returns_false(self):
        """Sun below 3° elevation is treated as below the horizon."""
        assert compute_sun_facing(make_hass(sun_ele=2.9), self.cfg(), self.FACADES) is False

    def test_elevation_at_3_is_not_below_horizon(self):
        """Elevation exactly 3° passes the horizon check."""
        result = compute_sun_facing(make_hass(sun_azi=180.0, sun_ele=3.0), self.cfg(), self.FACADES)
        assert result is True

    # ── Azimuth cone ──────────────────────────────────────────────────────

    def test_sun_on_facade_axis(self):
        """Sun exactly on the facade axis → True."""
        assert compute_sun_facing(make_hass(sun_azi=180.0), self.cfg(), self.FACADES) is True

    def test_sun_inside_left_boundary(self):
        """Sun 1° inside the left boundary → True."""
        # facade=180, angle_left=85 → left edge at 95°; sun at 96° is inside
        assert compute_sun_facing(make_hass(sun_azi=96.0), self.cfg(angle_left=85), self.FACADES) is True

    def test_sun_on_left_boundary(self):
        """Sun exactly on the left edge → True (inclusive)."""
        assert compute_sun_facing(make_hass(sun_azi=95.0), self.cfg(angle_left=85), self.FACADES) is True

    def test_sun_outside_left_boundary(self):
        """Sun 1° outside the left boundary → False."""
        assert compute_sun_facing(make_hass(sun_azi=94.0), self.cfg(angle_left=85), self.FACADES) is False

    def test_sun_inside_right_boundary(self):
        """Sun 1° inside the right boundary → True."""
        assert compute_sun_facing(make_hass(sun_azi=264.0), self.cfg(angle_right=85), self.FACADES) is True

    def test_sun_outside_right_boundary(self):
        """Sun 1° outside the right boundary → False."""
        assert compute_sun_facing(make_hass(sun_azi=266.0), self.cfg(angle_right=85), self.FACADES) is False

    # ── Azimuth wrap-around (facade near 0°/360°) ─────────────────────────

    def test_wraparound_facade_north_sun_inside(self):
        """Facade at 10°, sun at 350° — should be inside the cone despite wrap."""
        # min_az = (10-85)%360 = 285, max_az = (10+85)%360 = 95  → arc crosses 0°
        facades = {"nord": {"azimuth": 10.0}}
        cfg = {"facade": "nord", "angle_left": 85.0, "angle_right": 85.0}
        assert compute_sun_facing(make_hass(sun_azi=350.0), cfg, facades) is True

    def test_wraparound_facade_north_sun_outside(self):
        """Same facade, sun at 200° — clearly outside."""
        facades = {"nord": {"azimuth": 10.0}}
        cfg = {"facade": "nord", "angle_left": 85.0, "angle_right": 85.0}
        assert compute_sun_facing(make_hass(sun_azi=200.0), cfg, facades) is False

    # ── Custom angles ─────────────────────────────────────────────────────

    def test_narrow_cone_inside(self):
        """Narrow cone (±10°): sun at 175° is inside."""
        assert compute_sun_facing(
            make_hass(sun_azi=175.0), self.cfg(angle_left=10, angle_right=10), self.FACADES
        ) is True

    def test_narrow_cone_outside(self):
        """Narrow cone (±10°): sun at 160° is outside."""
        assert compute_sun_facing(
            make_hass(sun_azi=160.0), self.cfg(angle_left=10, angle_right=10), self.FACADES
        ) is False

    def test_asymmetric_angles(self):
        """angle_left != angle_right: each side respected independently."""
        # facade=180, left=30, right=10 → arc [150..190]
        cfg = {"facade": "sud", "angle_left": 30.0, "angle_right": 10.0}
        assert compute_sun_facing(make_hass(sun_azi=155.0), cfg, self.FACADES) is True   # inside left
        assert compute_sun_facing(make_hass(sun_azi=145.0), cfg, self.FACADES) is False  # outside left
        assert compute_sun_facing(make_hass(sun_azi=188.0), cfg, self.FACADES) is True   # inside right
        assert compute_sun_facing(make_hass(sun_azi=192.0), cfg, self.FACADES) is False  # outside right


# ════════════════════════════════════════════════════════════════════════════
# compute_shade_sync
# ════════════════════════════════════════════════════════════════════════════

class TestComputeShadeSync:
    """Tests for compute_shade_sync."""

    # ── Prerequisites ─────────────────────────────────────────────────────

    def test_sun_unavailable_returns_default(self, base_cfg):
        """sun.sun unavailable → (default_pos, False)."""
        pos, update = compute_shade_sync(make_hass(sun_ok=False), "cover.test", base_cfg)
        assert pos == 100
        assert update is False

    def test_below_min_elevation_returns_default_position(self, base_cfg):
        """Sun below min_elevation → default position (100%).

        No cover state → should_update=True (first run: move to default).
        """
        pos, update = compute_shade_sync(make_hass(sun_ele=3.0), "cover.test", base_cfg)
        assert pos == 100
        assert update is True  # no existing state → always update on first run

    def test_below_min_elevation_no_update_when_already_at_default(self, base_cfg):
        """Cover already at default position → diff=0 < threshold → no update."""
        pos, update = compute_shade_sync(
            make_hass(sun_ele=3.0, cover_pos=100, minutes_since_move=10), "cover.test", base_cfg
        )
        assert pos == 100
        assert update is False

    def test_above_max_elevation_returns_default_position(self, base_cfg):
        """Sun above max_elevation → default position (100%).

        No cover state → should_update=True (first run).
        """
        pos, update = compute_shade_sync(make_hass(sun_ele=85.0), "cover.test", base_cfg)
        assert pos == 100
        assert update is True

    def test_above_max_elevation_no_update_when_already_at_default(self, base_cfg):
        """Cover already at default position → no update."""
        pos, update = compute_shade_sync(
            make_hass(sun_ele=85.0, cover_pos=100, minutes_since_move=10), "cover.test", base_cfg
        )
        assert pos == 100
        assert update is False

    def test_outside_azimuth_fov_returns_default(self, base_cfg):
        """Sun outside azimuth FOV → default position."""
        # facade=180, degrees=90 → FOV ±90° → sun at 10° is outside
        pos, _ = compute_shade_sync(make_hass(sun_azi=10.0, sun_ele=45.0), "cover.test", base_cfg)
        assert pos == 100

    # ── Physics formula ───────────────────────────────────────────────────

    def test_physics_gamma_zero(self, base_cfg):
        """gamma=0 (sun directly on facade axis): h = distance * tan(elevation).

        distance=0.5, h_max=2.0, elevation=45° → h = 0.5 * tan(45°) = 0.5m
        position = 100 * (0.5 - 0) / (2.0 - 0) = 25%
        """
        pos, _ = compute_shade_sync(make_hass(sun_azi=180.0, sun_ele=45.0), "cover.test", base_cfg)
        assert pos == 25

    def test_physics_gamma_nonzero(self, base_cfg):
        """gamma≠0: h = (distance / cos(gamma)) * tan(elevation).

        sun_azi=150, facade=180 → gamma=30°
        h = (0.5 / cos(30°)) * tan(45°) = 0.5 / 0.866 ≈ 0.577m
        position = 100 * 0.577 / 2.0 ≈ 29%
        """
        pos, _ = compute_shade_sync(make_hass(sun_azi=150.0, sun_ele=45.0), "cover.test", base_cfg)
        expected = round(100.0 * (0.5 / math.cos(math.radians(30))) * math.tan(math.radians(45)) / 2.0)
        assert pos == expected

    # ── Clamping ──────────────────────────────────────────────────────────

    def test_position_clamped_to_minimum(self, base_cfg):
        """Very low sun → computed position below minimum_position (10%) → clamped."""
        # elevation=6°, gamma=0: h = 0.5 * tan(6°) ≈ 0.052m → ~2.6% → clamped to 10
        pos, _ = compute_shade_sync(make_hass(sun_azi=180.0, sun_ele=6.0), "cover.test", base_cfg)
        assert pos == 10

    def test_position_clamped_to_100(self, base_cfg):
        """Very tall shadow → position clamped to 100%."""
        # Large distance pushes h >> h_max
        base_cfg["shade"]["distance"] = 50.0
        pos, _ = compute_shade_sync(make_hass(sun_azi=180.0, sun_ele=45.0), "cover.test", base_cfg)
        assert pos == 100

    # ── Change threshold ──────────────────────────────────────────────────

    def test_diff_below_threshold_no_update(self, base_cfg):
        """Current position matches computed → diff < threshold → no move."""
        # computed=25 (gamma=0, ele=45°), current=25 → diff=0 < threshold=5
        pos, update = compute_shade_sync(
            make_hass(sun_azi=180.0, sun_ele=45.0, cover_pos=25), "cover.test", base_cfg
        )
        assert update is False
        assert pos == 25  # unchanged

    def test_diff_within_threshold_snaps_to_current(self, base_cfg):
        """Diff within threshold: returned position is current, not computed."""
        # computed=25, current=27 → diff=2 < threshold=5
        pos, update = compute_shade_sync(
            make_hass(sun_azi=180.0, sun_ele=45.0, cover_pos=27), "cover.test", base_cfg
        )
        assert update is False
        assert pos == 27

    def test_diff_just_below_threshold_no_update(self, base_cfg):
        """Diff strictly below threshold → no update (operator is <, not <=).

        computed=25, current=29 → diff=4 < threshold=5 → no move.
        """
        pos, update = compute_shade_sync(
            make_hass(sun_azi=180.0, sun_ele=45.0, cover_pos=29), "cover.test", base_cfg
        )
        assert update is False
        assert pos == 29  # snapped to current

    def test_diff_at_threshold_boundary_triggers_update(self, base_cfg):
        """Diff exactly equal to threshold → update (< is strict, not <=).

        computed=25, current=30 → diff=5 = threshold=5 → proceeds to timeout check.
        With minutes_since_move=10 > time_out=2 → update=True.
        """
        pos, update = compute_shade_sync(
            make_hass(sun_azi=180.0, sun_ele=45.0, cover_pos=30, minutes_since_move=10),
            "cover.test", base_cfg,
        )
        assert update is True

    # ── Time-out ──────────────────────────────────────────────────────────

    def test_timeout_elapsed_triggers_update(self, base_cfg):
        """diff > threshold AND timeout elapsed → (computed, True)."""
        # computed=25, current=60, diff=35 > 5, 10min > time_out=2min
        pos, update = compute_shade_sync(
            make_hass(sun_azi=180.0, sun_ele=45.0, cover_pos=60, minutes_since_move=10),
            "cover.test", base_cfg,
        )
        assert update is True
        assert pos == 25

    def test_timeout_not_elapsed_blocks_update(self, base_cfg):
        """diff > threshold BUT timeout not elapsed → (computed, False)."""
        pos, update = compute_shade_sync(
            make_hass(sun_azi=180.0, sun_ele=45.0, cover_pos=60, minutes_since_move=1),
            "cover.test", base_cfg,
        )
        assert update is False

    # ── Edge cases ────────────────────────────────────────────────────────

    def test_no_cover_state_always_updates(self, base_cfg):
        """No existing cover state → should_update=True (first run)."""
        _, update = compute_shade_sync(make_hass(sun_azi=180.0, sun_ele=45.0), "cover.test", base_cfg)
        assert update is True

    def test_ombre_mode_overrides_default_position(self, base_cfg):
        """Mode 'Ombre' with fixed position overrides default_position."""
        base_cfg["modes"]["Ombre"] = 50
        # sun outside FOV → should return Ombre position (50), not default_position (100)
        pos, _ = compute_shade_sync(make_hass(sun_ele=3.0), "cover.test", base_cfg)
        assert pos == 50

    def test_zero_division_fallback_is_safe(self, base_cfg):
        """gamma=±90° → cos(gamma)=0 → ZeroDivisionError handled, returns valid position."""
        # facade=180, sun_azi=90 → gamma=90°
        pos, _ = compute_shade_sync(make_hass(sun_azi=90.0, sun_ele=45.0), "cover.test", base_cfg)
        assert 0 <= pos <= 100

    def test_equal_h_max_h_min_no_division(self, base_cfg):
        """h_max == h_min → _h2perc returns 0 without ZeroDivisionError."""
        base_cfg["shade"]["max_height"] = 1.0
        base_cfg["shade"]["min_height"] = 1.0
        pos, _ = compute_shade_sync(make_hass(sun_azi=180.0, sun_ele=45.0), "cover.test", base_cfg)
        assert pos >= 0  # no crash
