import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cover_extender.const import DOMAIN


# ─────────────────────────────────────────────────────────────
# Constante importée directement par test_shade.py
# ─────────────────────────────────────────────────────────────

BASE_SHADE_CFG = {
    "facade": 180,
    "min_elevation": 5,
    "max_elevation": 60,
    "h_min": 0.2,
    "h_max": 0.8,
    "gamma": 1.0,
    "timeout": 300,
    # clés utilisées dynamiquement dans certains tests
    "shade": {
        "distance": 100.0,
        "max_height": 1.0,
    },
    "modes": {},
}


# ─────────────────────────────────────────────────────────────
# Helper (FACTORY) utilisé par test_shade.py
# ⚠️ Ce n’est PAS une fixture
# ─────────────────────────────────────────────────────────────

def make_hass(
    hass: HomeAssistant,
    *,
    sun_azi: float | None = None,
    sun_ele: float | None = None,
    sun_ok: bool = True,
    cover_pos: int | None = None,
    minutes_since_move: int | None = None,
) -> HomeAssistant:
    """
    Factory utilisée par test_shade.py pour préparer un hass
    avec un état du soleil et du cover.
    """

    # ── Soleil ───────────────────────────────────────────────
    if sun_ok:
        hass.states.async_set(
            "sun.sun",
            "above_horizon",
            {
                "azimuth": sun_azi,
                "elevation": sun_ele,
            },
        )
    else:
        hass.states.async_set("sun.sun", "unavailable")

    # ── Cover ────────────────────────────────────────────────
    if cover_pos is not None:
        attrs = {"current_position": cover_pos}

        if minutes_since_move is not None:
            attrs["last_changed"] = hass.loop.time() - (minutes_since_move * 60)

        hass.states.async_set("cover.test", "open", attrs)

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
    # ⚠️ CRUCIAL : initialisation du namespace de l’intégration
    hass.data.setdefault(DOMAIN, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cover Extender",
        data={},
        options={},
        unique_id="test",
    )
    entry.add_to_hass(hass)
    return entry
