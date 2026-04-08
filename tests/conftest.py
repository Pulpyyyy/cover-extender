import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from custom_components.cover_extender.const import DOMAIN


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
