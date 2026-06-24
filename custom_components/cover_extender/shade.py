"""Solar geometry helpers for cover_extender.

Pure functions: no hass state mutations, fully testable without HA.
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_FACADE,
    CONF_SHADING,
    CONF_MODES,
    CONF_ANGLE_LEFT,
    CONF_ANGLE_RIGHT,
    CONF_AZIMUTH,
    DATA_FACADES,
)

_LOGGER = logging.getLogger(__name__)


def compute_facade_lit(
    hass: HomeAssistant,
    facade_name: str,
    facades_cfg: dict[str, Any],
    angle_left: float = 85.0,
    angle_right: float = 85.0,
) -> bool | None:
    """Return True if the sun illuminates the given facade, False if not, None if unavailable."""
    sun_st = hass.states.get("sun.sun")
    if not sun_st:
        return None

    elevation = float(sun_st.attributes.get("elevation", 0))
    if elevation < 3:
        return False

    azimuth = float(sun_st.attributes.get("azimuth", 0))
    axe = float(facades_cfg.get(facade_name, {}).get(CONF_AZIMUTH, 180.0))

    min_az = (axe - angle_left) % 360
    max_az = (axe + angle_right) % 360

    if min_az < max_az:
        return min_az <= azimuth <= max_az
    return azimuth >= min_az or azimuth <= max_az


def compute_sun_facing(
    hass: HomeAssistant,
    cfg: dict[str, Any],
    facades_cfg: dict[str, Any],
) -> bool | None:
    """Return True if the sun is facing the cover (per-cover angles, per-facade azimuth)."""
    facade = cfg.get(CONF_FACADE)
    if not facade:
        return None
    return compute_facade_lit(
        hass, facade, facades_cfg,
        angle_left=float(cfg.get(CONF_ANGLE_LEFT, 85.0)),
        angle_right=float(cfg.get(CONF_ANGLE_RIGHT, 85.0)),
    )


def compute_shade_sync(
    hass: HomeAssistant,
    entity_id: str,
    cfg: dict[str, Any],
) -> tuple[int, bool]:
    """Compute the shade position and should_update flag (synchronous).

    Applies the change_threshold: if the difference between the computed position
    and the current position is below the threshold, the current position is
    returned unchanged and should_update is False.

    Also respects time_out: if the cover was last updated less than time_out
    minutes ago, should_update is False even if the position changed enough.

    Returns (position_percent, should_update).
    """
    auto_shade = cfg.get(CONF_SHADING, {})

    distance  = float(auto_shade.get("distance",         0.3))
    h_max     = float(auto_shade.get("max_height",       1.5))
    h_min     = float(auto_shade.get("min_height",       0.0))
    degrees   = float(auto_shade.get("degrees",          90))
    max_elev  = float(auto_shade.get("max_elevation",    90))
    min_elev  = float(auto_shade.get("min_elevation",    5))
    min_pos   = float(auto_shade.get("minimum_position", 10))
    threshold = float(auto_shade.get("change_threshold", 5))
    time_out  = float(auto_shade.get("time_out",         1))

    modes_dict  = cfg.get(CONF_MODES, {})
    shade_fixed = modes_dict.get("Ombre")
    default_pos = (
        float(shade_fixed)
        if shade_fixed is not None
        else float(auto_shade.get("default_position", 100))
    )

    facade      = cfg.get(CONF_FACADE, "south")
    facades_cfg = hass.data[DOMAIN].get(DATA_FACADES, {})
    win_azi     = float(facades_cfg.get(facade, {}).get(CONF_AZIMUTH, 180.0))

    sun_st = hass.states.get("sun.sun")
    if not sun_st:
        return int(default_pos), False

    sun_azi = float(sun_st.attributes.get("azimuth",   180))
    sun_ele = float(sun_st.attributes.get("elevation", 0))

    deg2rad          = math.pi / 180
    fov              = deg2rad * degrees
    alpha            = deg2rad * sun_ele
    gamma            = deg2rad * ((win_azi - sun_azi + 180) % 360 - 180)
    default_height_m = default_pos / 100.0 * h_max

    def _h2perc(h: float) -> float:
        return 100.0 * (h - h_min) / (h_max - h_min) if h_max != h_min else 0.0

    def _clip(x: float, lo: float, hi: float) -> float:
        return max(min(x, hi), lo)

    in_fov = (-fov <= gamma <= fov) and (deg2rad * min_elev <= alpha <= deg2rad * max_elev)
    if not in_fov:
        position = int(_clip(round(_h2perc(default_height_m)), 0, 100))
        _LOGGER.debug(
            "shade %s: sun outside FOV (azi_diff=%.1f°, elev=%.1f°) → default position %d%%",
            entity_id, math.degrees(gamma), math.degrees(alpha), position,
        )
    else:
        try:
            h = (distance / math.cos(gamma)) * math.tan(alpha)
        except ZeroDivisionError:
            h = default_height_m
        position = int(_clip(round(_h2perc(h)), min_pos, 100))
        _LOGGER.debug(
            "shade %s: sun inside FOV (azi_diff=%.1f°, elev=%.1f°) → computed position %d%%",
            entity_id, math.degrees(gamma), math.degrees(alpha), position,
        )

    cover_st = hass.states.get(entity_id)
    if cover_st:
        current = int(cover_st.attributes.get("current_position", position))
        diff = abs(current - position)
        if diff < threshold:
            _LOGGER.debug(
                "shade %s: diff %d%% below threshold %d%% → no move",
                entity_id, diff, threshold,
            )
            return current, False

        # Use last_changed (not last_updated): the coordinator re-injects custom
        # attributes (sun_facing, memory, modes) very frequently, which bumps
        # last_updated on every write and would falsely reset the time_out throttle.
        # last_changed only moves when the cover's state actually changes.
        time_ok = dt_util.utcnow() - timedelta(minutes=time_out) >= cover_st.last_changed
        if not time_ok:
            _LOGGER.debug(
                "shade %s: time_out %.1f min not elapsed → no move",
                entity_id, time_out,
            )
        return position, time_ok

    return position, True
