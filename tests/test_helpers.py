"""Tests for helpers.py — resolve_mode_position and build_extra_attrs."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.cover_extender.helpers import resolve_mode_position, build_extra_attrs
from custom_components.cover_extender.const import (
    ATTR_FACADE,
    ATTR_MODES,
    ATTR_ENABLE_AUTO_SHADE,
)


# ════════════════════════════════════════════════════════════════════════════
# resolve_mode_position
# ════════════════════════════════════════════════════════════════════════════

class TestResolveModePosition:

    def make_hass(self, entity_state: str | None = None) -> MagicMock:
        hass = MagicMock()
        if entity_state is None:
            hass.states.get.return_value = None
        else:
            st = MagicMock()
            st.state = entity_state
            hass.states.get.return_value = st
        return hass

    # ── None passthrough ──────────────────────────────────────────────────

    def test_none_returns_none(self):
        """raw=None → None (auto-shade mode, no fixed position)."""
        assert resolve_mode_position(MagicMock(), None) is None

    # ── Integer / float passthrough ───────────────────────────────────────

    def test_int_returns_int(self):
        assert resolve_mode_position(MagicMock(), 40) == 40

    def test_float_returns_int(self):
        assert resolve_mode_position(MagicMock(), 75.9) == 75

    def test_zero_returns_zero(self):
        assert resolve_mode_position(MagicMock(), 0) == 0

    def test_hundred_returns_hundred(self):
        assert resolve_mode_position(MagicMock(), 100) == 100

    # ── Entity ID resolution ──────────────────────────────────────────────

    def test_entity_id_numeric_state(self):
        """raw=entity_id with numeric state → int."""
        hass = self.make_hass("42")
        assert resolve_mode_position(hass, "input_number.position") == 42

    def test_entity_id_float_state(self):
        """raw=entity_id with float string state → int."""
        hass = self.make_hass("33.7")
        assert resolve_mode_position(hass, "input_number.position") == 33

    def test_entity_id_not_found_returns_none(self):
        """Entity not in state machine → None (with warning)."""
        hass = self.make_hass(None)
        assert resolve_mode_position(hass, "input_number.missing") is None

    def test_entity_id_non_numeric_state_returns_none(self):
        """Entity has non-numeric state → None (with warning)."""
        hass = self.make_hass("unavailable")
        assert resolve_mode_position(hass, "input_number.broken") is None

    def test_entity_id_empty_state_returns_none(self):
        """Entity has empty string state → None."""
        hass = self.make_hass("")
        assert resolve_mode_position(hass, "input_number.empty") is None


# ════════════════════════════════════════════════════════════════════════════
# build_extra_attrs
# ════════════════════════════════════════════════════════════════════════════

class TestBuildExtraAttrs:

    # ── Minimal config ────────────────────────────────────────────────────

    def test_empty_config_has_auto_shade_key(self):
        """auto_shade key is always present, even on empty config."""
        attrs = build_extra_attrs({})
        assert ATTR_ENABLE_AUTO_SHADE in attrs
        assert attrs[ATTR_ENABLE_AUTO_SHADE] is False

    def test_no_memory_key_when_none(self):
        """memory not included when value is None."""
        attrs = build_extra_attrs({})
        assert "memory" not in attrs

    # ── Optional fields ───────────────────────────────────────────────────

    def test_facade_included_when_present(self):
        attrs = build_extra_attrs({"facade": "sud"})
        assert attrs[ATTR_FACADE] == "sud"

    def test_facade_absent_when_not_configured(self):
        attrs = build_extra_attrs({})
        assert ATTR_FACADE not in attrs

    def test_entity_picture_included_when_present(self):
        attrs = build_extra_attrs({"entity_picture": "https://example.com/img.jpg"})
        assert attrs["entity_picture"] == "https://example.com/img.jpg"

    def test_entity_picture_absent_when_not_configured(self):
        attrs = build_extra_attrs({})
        assert "entity_picture" not in attrs

    def test_modes_included_as_copy(self):
        """modes dict is included and is a copy (mutations don't affect cfg)."""
        cfg = {"modes": {"Day": 40, "Night": 0}}
        attrs = build_extra_attrs(cfg)
        assert attrs[ATTR_MODES] == {"Day": 40, "Night": 0}
        attrs[ATTR_MODES]["Extra"] = 50
        assert "Extra" not in cfg["modes"]

    def test_modes_absent_when_empty(self):
        attrs = build_extra_attrs({"modes": {}})
        assert ATTR_MODES not in attrs

    # ── Auto shade flag ───────────────────────────────────────────────────

    def test_auto_shade_true_when_enabled(self):
        cfg = {"shade": {"enable": True}}
        assert build_extra_attrs(cfg)[ATTR_ENABLE_AUTO_SHADE] is True

    def test_auto_shade_false_when_disabled(self):
        cfg = {"shade": {"enable": False}}
        assert build_extra_attrs(cfg)[ATTR_ENABLE_AUTO_SHADE] is False

    def test_auto_shade_false_when_shade_key_missing(self):
        assert build_extra_attrs({})[ATTR_ENABLE_AUTO_SHADE] is False

    # ── Memory ────────────────────────────────────────────────────────────

    def test_memory_included_when_provided(self):
        attrs = build_extra_attrs({}, memory=65)
        assert attrs["memory"] == 65

    def test_memory_zero_included(self):
        """Memory=0 (fully closed) must be included, not treated as falsy."""
        attrs = build_extra_attrs({}, memory=0)
        assert "memory" in attrs
        assert attrs["memory"] == 0

    # ── Full config ───────────────────────────────────────────────────────

    def test_full_config_all_keys_present(self):
        cfg = {
            "facade": "est",
            "entity_picture": "https://example.com/cover.jpg",
            "modes": {"Day": 40},
            "shade": {"enable": True},
        }
        attrs = build_extra_attrs(cfg, memory=50)
        assert attrs[ATTR_FACADE] == "est"
        assert attrs["entity_picture"] == "https://example.com/cover.jpg"
        assert attrs[ATTR_MODES] == {"Day": 40}
        assert attrs[ATTR_ENABLE_AUTO_SHADE] is True
        assert attrs["memory"] == 50
