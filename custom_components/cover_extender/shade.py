"""Solar geometry helpers for cover_extender.

Pure functions: no hass state mutations, fully testable without HA.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_FACADE,
    CONF_SHADING,
    CONF_ANGLE_LEFT,
    CONF_ANGLE_RIGHT,
    CONF_AZIMUTH,
    CONF_TILT,
    DATA_FACADES,
    FLAT_TILT,
    WALL_TILT,
)

_LOGGER = logging.getLogger(__name__)


# ── The sector: where the sun must be to face a window ────────────────────────
# One rule for everything that asks "is the sun in front of this window?": the
# "sun facing" sensor, solar gain and shading.

def sun_offset(facade_azimuth: float, sun_azimuth: float) -> float:
    """The sun's angle from the facade's axis, in ]-180, 180].

    Positive to the left of someone looking out of the window (towards the
    east for a south facade), negative to the right.
    """
    return (facade_azimuth - sun_azimuth + 180) % 360 - 180


def in_sector(offset: float, angle_left: float, angle_right: float) -> bool:
    """Whether a sun at *offset* (see sun_offset) is within the cover's angles."""
    return -angle_right <= offset <= angle_left


def facade_geometry(facades_cfg: dict[str, Any], facade_name: str | None) -> tuple[float, float]:
    """A facade's (azimuth, tilt). An unknown facade faces due south, upright."""
    facade = facades_cfg.get(facade_name, {}) if facade_name else {}
    return (
        float(facade.get(CONF_AZIMUTH, 180.0)),
        float(facade.get(CONF_TILT, WALL_TILT)),
    )


def tilt_kind(tilt: float) -> str:
    """The kind of window a slope makes: "wall", "roof" or "flat"."""
    if tilt >= WALL_TILT:
        return "wall"
    return "flat" if tilt < FLAT_TILT else "roof"


def cos_incidence(elevation: float, offset: float, tilt: float) -> float:
    """Cosine of the angle between the sun and the perpendicular to the glass.

    *tilt* is the glass's angle with the horizontal. Positive when the sun
    shines on the outer face. For a wall (90°) this is cos(elevation) times
    cos(offset): positive exactly when the sun is in front of the wall.
    """
    a, g, b = math.radians(elevation), math.radians(offset), math.radians(tilt)
    return math.sin(a) * math.cos(b) + math.cos(a) * math.sin(b) * math.cos(g)


def faces_glass(elevation: float, offset: float, tilt: float) -> bool:
    """Whether the sun is on the outer side of the glass.

    A wall only sees the sky in front of it. A roof also sees part of the sky
    behind it: the sun touches the glass once it is above the roof's plane.
    A sun exactly in the plane still counts, as it always did on a wall at 90°.
    """
    return cos_incidence(elevation, offset, tilt) >= -1e-9


def sun_height(elevation: float, offset: float, tilt: float) -> float:
    """The sun's height on the cover's height range, in [0, 180].

    Read from the horizon in front of the window, over the zenith, and on a
    roof down the other side: a sun 60° high behind a roof is at 120°. One
    range then holds a single cone, whatever the slope. A wall never sees the
    sun behind it, and a flat window has neither front nor back, so for both
    it is simply the elevation.
    """
    if not FLAT_TILT <= tilt < WALL_TILT or abs(offset) <= 90:
        return elevation
    return 180.0 - elevation


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
    axe, tilt = facade_geometry(facades_cfg, facade_name)
    offset = sun_offset(axe, azimuth)
    return in_sector(offset, angle_left, angle_right) and faces_glass(elevation, offset, tilt)


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
    last_move: datetime | None = None,
) -> tuple[int, bool]:
    """Compute the shade position and should_update flag (synchronous).

    Applies the change_threshold: if the difference between the computed position
    and the current position is below the threshold, the current position is
    returned unchanged and should_update is False.

    Also respects time_out: *last_move* is the timestamp of the last known cover
    movement (command sent by the coordinator OR position change observed in the
    state machine — remote controls, HA UI, other automations). If it is less
    than time_out minutes old, should_update is False even if the position
    changed enough. Pass None to bypass the throttle.

    The sun counts as in front of the window when it lies within the cover's
    own angle to the left and angle to the right of the facade's axis, the very
    sector the "sun facing" sensor and solar gain use, on the outer side of the
    glass, and between the minimum and maximum heights (see sun_height). On a
    wall the glass test is what keeps a sun behind it out, whatever the angles.

    The cover then leaves open just enough glass for the sunlit patch to reach
    *distance* into the room, measured at the level of the window's lower edge:
    an open length of distance * sin(elevation) / cos(incidence), along the
    glass. On a wall that is the familiar distance * tan(elevation) / cos(offset).
    A flat window has no patch to hold near a wall: the sun falls straight in,
    and the cover simply takes its sun_position.

    Returns (position_percent, should_update).
    """
    auto_shade = cfg.get(CONF_SHADING, {})

    distance  = float(auto_shade.get("distance",         0.3))
    h_max     = float(auto_shade.get("max_height",       1.5))
    h_min     = float(auto_shade.get("min_height",       0.0))
    max_elev  = float(auto_shade.get("max_elevation",    180))
    min_elev  = float(auto_shade.get("min_elevation",    5))
    min_pos   = float(auto_shade.get("minimum_position", 10))
    threshold = float(auto_shade.get("change_threshold", 5))
    time_out  = float(auto_shade.get("time_out",         1))

    default_pos = float(auto_shade.get("default_position", 100))
    sun_pos     = float(auto_shade.get("sun_position",     30))

    angle_left  = float(cfg.get(CONF_ANGLE_LEFT, 85.0))
    angle_right = float(cfg.get(CONF_ANGLE_RIGHT, 85.0))

    facades_cfg   = hass.data[DOMAIN].get(DATA_FACADES, {})
    win_azi, tilt = facade_geometry(facades_cfg, cfg.get(CONF_FACADE, "south"))

    sun_st = hass.states.get("sun.sun")
    if not sun_st:
        return int(default_pos), False

    sun_azi = float(sun_st.attributes.get("azimuth",   180))
    sun_ele = float(sun_st.attributes.get("elevation", 0))

    gamma_deg        = sun_offset(win_azi, sun_azi)
    cos_inc          = cos_incidence(sun_ele, gamma_deg, tilt)
    height           = sun_height(sun_ele, gamma_deg, tilt)
    # Map the default % onto the [h_min, h_max] range so that _h2perc gives
    # back exactly default_pos (was wrong when min_height > 0).
    default_height_m = h_min + default_pos / 100.0 * (h_max - h_min)

    def _h2perc(h: float) -> float:
        return 100.0 * (h - h_min) / (h_max - h_min) if h_max != h_min else 0.0

    def _clip(x: float, lo: float, hi: float) -> float:
        return max(min(x, hi), lo)

    facing = (
        in_sector(gamma_deg, angle_left, angle_right)
        and faces_glass(sun_ele, gamma_deg, tilt)
        and min_elev <= height <= max_elev
    )
    if not facing:
        position = int(_clip(round(_h2perc(default_height_m)), 0, 100))
        _LOGGER.debug(
            "shade %s: sun outside the sector (azi_diff=%.1f°, elev=%.1f°, tilt=%.0f°) → default position %d%%",
            entity_id, gamma_deg, sun_ele, tilt, position,
        )
    elif tilt < FLAT_TILT:
        position = int(_clip(round(sun_pos), 0, 100))
        _LOGGER.debug(
            "shade %s: sun on a flat window (elev=%.1f°) → sun position %d%%",
            entity_id, sun_ele, position,
        )
    else:
        if cos_inc > 1e-9:
            h = distance * math.sin(math.radians(sun_ele)) / cos_inc
        else:
            h = default_height_m
        position = int(_clip(round(_h2perc(h)), min_pos, 100))
        _LOGGER.debug(
            "shade %s: sun inside the sector (azi_diff=%.1f°, elev=%.1f°, tilt=%.0f°) → computed position %d%%",
            entity_id, gamma_deg, sun_ele, tilt, position,
        )

    cover_st = hass.states.get(entity_id)
    if cover_st:
        # current_position may exist with a None value (position unknown / moving)
        raw_current = cover_st.attributes.get("current_position")
        current = position if raw_current is None else int(raw_current)
        diff = abs(current - position)
        if diff < threshold:
            _LOGGER.debug(
                "shade %s: diff %d%% below threshold %d%% → no move",
                entity_id, diff, threshold,
            )
            return current, False

    time_ok = (
        last_move is None
        or dt_util.utcnow() - last_move >= timedelta(minutes=time_out)
    )
    if not time_ok:
        _LOGGER.debug(
            "shade %s: time_out %.1f min not elapsed since last move → no move",
            entity_id, time_out,
        )
    return position, time_ok
