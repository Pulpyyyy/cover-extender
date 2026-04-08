import pytest
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cover_extender.const import DOMAIN


# ─────────────────────────────────────────────────────────────
# Helpers utilisés par test_shade.py (DOIT être une FONCTION)
# ─────────────────────────────────────────────────────────────

def make_hass(hass: HomeAssistant) -> HomeAssistant:
    """Return the Home Assistant instance (helper, not a fixture)."""
    return hass


# ─────────────────────────────────────────────────────────────
# Fixtures utilisées par test_shade.py
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def base_cfg():
    return {
        "facade": 180,
        "min_elevation": 5,
        "max_elevation": 60,
        "h_min": 0.2,
        "h_max": 0.8,
        "gamma": 1.0,
        "timeout": 300,
    }


# ─────────────────────────────────────────────────────────────
# Fixture pour binary_sensor / switch / select
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config_entry(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cover Extender",
        data={},
        options={},
        unique_id="test",
    )
    entry.add_to_hass(hass)
    return entry
