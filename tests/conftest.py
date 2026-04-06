"""Shared fixtures for cover_extender tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.cover_extender.const import DOMAIN, DATA_FACADES

# ── Default shading config used across tests ──────────────────────────────────

BASE_SHADE_CFG: dict = {
    "facade": "sud",
    "shade": {
        "enable": True,
        "distance": 0.5,
        "max_height": 2.0,
        "min_height": 0.0,
        "degrees": 90,
        "max_elevation": 80,
        "min_elevation": 5,
        "minimum_position": 10,
        "default_position": 100,
        "change_threshold": 5,
        "time_out": 2,
    },
    "modes": {},
}


# ── hass factory ─────────────────────────────────────────────────────────────

def make_hass(
    sun_azi: float = 180.0,
    sun_ele: float = 45.0,
    sun_ok: bool = True,
    cover_pos: int | None = None,
    minutes_since_move: float = 10.0,
    facades: dict | None = None,
) -> MagicMock:
    """Return a minimal hass mock suitable for shade/sun-facing tests.

    Args:
        sun_azi:            Sun azimuth in degrees.
        sun_ele:            Sun elevation in degrees.
        sun_ok:             False → sun.sun state returns None (unavailable).
        cover_pos:          current_position attribute of cover.test, or None (no state).
        minutes_since_move: How long ago the cover last moved (for time_out checks).
        facades:            Override the default facades dict.
    """
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            DATA_FACADES: facades if facades is not None else {"sud": {"azimuth": 180.0}}
        }
    }

    def _get_state(entity_id: str) -> MagicMock | None:
        if entity_id == "sun.sun":
            if not sun_ok:
                return None
            st = MagicMock()
            st.attributes = {"azimuth": sun_azi, "elevation": sun_ele}
            return st

        if entity_id == "cover.test":
            if cover_pos is None:
                return None
            st = MagicMock()
            st.attributes = {"current_position": cover_pos}
            st.last_updated = (
                datetime.now(timezone.utc) - timedelta(minutes=minutes_since_move)
            )
            return st

        return None

    hass.states.get.side_effect = _get_state
    return hass


# ── pytest fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def base_cfg() -> dict:
    """Return a deep copy of BASE_SHADE_CFG."""
    import copy
    return copy.deepcopy(BASE_SHADE_CFG)


@pytest.fixture
def south_facades() -> dict:
    """South-facing facade at 180°."""
    return {"sud": {"azimuth": 180.0}}
