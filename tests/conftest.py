import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.cover_extender.const import DOMAIN


# ─────────────────────────────────────────────────────────────
# Fixtures EXISTANTES utilisées par test_shade.py
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def make_hass(hass: HomeAssistant):
    """Return a Home Assistant instance (compat)."""
    return hass


BASE_SHADE_CFG = {
    "facade": 180,
    "min_elevation": 5,
    "max_elevation": 60,
    "h_min": 0.2,
    "h_max": 0.8,
    "gamma": 1.0,
    "timeout": 300,
}


# ─────────────────────────────────────────────────────────────
# Nouvelle fixture pour binary_sensor / switch / select
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config_entry(hass: HomeAssistant):
    """Mock a config entry for cover_extender."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Cover Extender",
        data={},
        options={},
        source="user",
        entry_id="test",
    )

    entry.add_to_hass(hass)
    return entry
