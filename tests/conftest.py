import pytest
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_SHOW_ENTITIES,
)


# ─────────────────────────────────────────────────────────────
# Constante importée directement par test_shade.py
# ─────────────────────────────────────────────────────────────

BASE_SHADE_CFG = {
    "facade": 180,
    "modes": {},
    "shade": {
        "distance": 0.5,
        "max_height": 2.0,
        "max_elevation": 60,
        "time_out": 2,
    },
}


# ─────────────────────────────────────────────────────────────
# Minimal mock hass used by make_hass (no HA event loop needed)
# ─────────────────────────────────────────────────────────────

class _MockState:
    def __init__(self, state, attributes, last_updated=None):
        self.state = state
        self.attributes = attributes or {}
        self.last_updated = last_updated or dt_util.utcnow()


class _MockStatesMachine:
    def __init__(self):
        self._store: dict = {}

    def async_set(self, entity_id, state, attributes=None, last_updated=None):
        self._store[entity_id] = _MockState(state, attributes, last_updated)

    def get(self, entity_id):
        return self._store.get(entity_id)


class _MockHass:
    def __init__(self):
        self.states = _MockStatesMachine()
        self.data: dict = {DOMAIN: {}}


# ─────────────────────────────────────────────────────────────
# Helper (FACTORY) utilisé par test_shade.py
# ⚠️ Ce n'est PAS une fixture
# ─────────────────────────────────────────────────────────────

def make_hass(
    *,
    sun_azi: float | None = None,
    sun_ele: float | None = None,
    sun_ok: bool = True,
    cover_pos: int | None = None,
    minutes_since_move: int | None = None,
) -> _MockHass:
    """
    Factory utilisée par test_shade.py pour préparer un hass mock
    avec un état du soleil et du cover.
    """
    hass = _MockHass()

    # ── Soleil ───────────────────────────────────────────────
    if sun_ok:
        hass.states.async_set(
            "sun.sun",
            "above_horizon",
            {
                "azimuth": sun_azi if sun_azi is not None else 0.0,
                "elevation": sun_ele if sun_ele is not None else 45.0,
            },
        )
    # if not sun_ok, leave sun.sun absent → states.get returns None

    # ── Cover ────────────────────────────────────────────────
    if cover_pos is not None:
        attrs = {"current_position": cover_pos}
        last_updated = None
        if minutes_since_move is not None:
            last_updated = dt_util.utcnow() - timedelta(minutes=minutes_since_move)
        hass.states.async_set("cover.test", "open", attrs, last_updated=last_updated)

    return hass


# ─────────────────────────────────────────────────────────────
# Fixture utilisée par test_shade.py (copie mutable)
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def base_cfg():
    """Retourne une copie pour éviter les effets de bord."""
    return {
        **BASE_SHADE_CFG,
        "shade": dict(BASE_SHADE_CFG["shade"]),
        "modes": dict(BASE_SHADE_CFG["modes"]),
    }


# ─────────────────────────────────────────────────────────────
# Fixture pour binary_sensor / switch / select
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config_entry(hass: HomeAssistant):
    hass.data.setdefault(DOMAIN, {})

    # Provide a minimal profile so platform setup creates at least one entity
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.test": {}}
    hass.data[DOMAIN][DATA_SHOW_ENTITIES] = {"auto_shade": True}

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cover Extender",
        data={},
        options={},
        unique_id="test",
    )
    entry.add_to_hass(hass)
    return entry
