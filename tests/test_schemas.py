"""Tests for load_covers_config in schemas.py."""
from __future__ import annotations

import pytest
import yaml

from custom_components.cover_extender.schemas import load_covers_config
from custom_components.cover_extender.const import DEFAULT_COMMAND_INTERVAL


class TestLoadCoversConfig:

    def test_file_not_found_returns_empty(self, hass):
        profiles, modes, facades, show, solar, interval = load_covers_config(
            hass, "/nonexistent/path/covers.yaml"
        )
        assert profiles == {}
        assert modes == {}
        assert facades == {}
        assert interval == DEFAULT_COMMAND_INTERVAL

    def test_relative_source_resolved_via_hass_config(self, hass):
        """Relative path → resolved through hass.config.path() (file not found → defaults)."""
        profiles, _, _, _, _, interval = load_covers_config(hass, "nonexistent_relative.yaml")
        assert profiles == {}
        assert interval == DEFAULT_COMMAND_INTERVAL

    def test_yaml_parse_error_returns_empty(self, hass, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("[\n", encoding="utf-8")  # unclosed bracket → YAMLError
        profiles, modes, facades, show, solar, interval = load_covers_config(
            hass, str(bad)
        )
        assert profiles == {}
        assert interval == DEFAULT_COMMAND_INTERVAL

    def test_empty_file_returns_empty(self, hass, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        profiles, modes, facades, show, solar, interval = load_covers_config(
            hass, str(f)
        )
        assert profiles == {}
        assert modes == {}
        assert facades == {}

    def test_valid_cover_profile_parsed(self, hass, tmp_path):
        cfg = {"cover.volet_sam": {"modes": {"Day": 40}}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        profiles, _, _, _, _, _ = load_covers_config(hass, str(f))
        assert "cover.volet_sam" in profiles
        assert profiles["cover.volet_sam"]["modes"]["Day"] == 40

    def test_facades_parsed(self, hass, tmp_path):
        cfg = {"facades": {"sud": {"azimuth": 180.0}}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, facades, _, _, _ = load_covers_config(hass, str(f))
        assert facades["sud"]["azimuth"] == 180.0

    def test_modes_section_parsed(self, hass, tmp_path):
        cfg = {"cover_extender_modes": {"Day": {"icon": "mdi:sun", "color": "orange"}}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, modes, _, _, _, _ = load_covers_config(hass, str(f))
        assert "Day" in modes
        assert modes["Day"]["icon"] == "mdi:sun"
        assert modes["Day"]["lock"] is False       # schema default
        assert modes["Day"]["behavior"] is None  # schema default

    def test_show_entities_parsed(self, hass, tmp_path):
        cfg = {"show_entities": {"sun_facing": True, "auto_shade": True, "solar_gain": True}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, show, _, _ = load_covers_config(hass, str(f))
        assert show["sun_facing"] is True
        assert show["auto_shade"] is True
        assert show["solar_gain"] is True

    def test_command_interval_parsed(self, hass, tmp_path):
        cfg = {"command_interval": 0.5}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, _, _, interval = load_covers_config(hass, str(f))
        assert interval == 0.5

    def test_negative_command_interval_uses_default(self, hass, tmp_path):
        cfg = {"command_interval": -1}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, _, _, interval = load_covers_config(hass, str(f))
        assert interval == DEFAULT_COMMAND_INTERVAL

    def test_solar_gain_global_parsed(self, hass, tmp_path):
        cfg = {"solar_gain": {"temperature_threshold": 22.0}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, _, solar, _ = load_covers_config(hass, str(f))
        assert solar["temperature_threshold"] == 22.0

    def test_solar_gain_with_entities(self, hass, tmp_path):
        cfg = {
            "solar_gain": {
                "temperature_entity": "sensor.temp",
                "weather_entity": "weather.home",
                "good_conditions": ["sunny"],
            }
        }
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, _, solar, _ = load_covers_config(hass, str(f))
        assert solar["temperature_entity"] == "sensor.temp"
        assert solar["weather_entity"] == "weather.home"
        assert "sunny" in solar["good_conditions"]

    def test_invalid_facade_skipped(self, hass, tmp_path):
        # azimuth "not_a_float" → vol.Coerce(float) raises Invalid → skipped
        cfg = {"facades": {"bad": {"azimuth": "not_a_float"}}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, facades, _, _, _ = load_covers_config(hass, str(f))
        assert "bad" not in facades

    def test_cover_mode_not_in_modes_section_warns_but_loads(self, hass, tmp_path):
        """Cover references a mode not in cover_extender_modes → warning, still loaded."""
        cfg = {"cover.test": {"modes": {"UnknownMode": 50}}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        profiles, _, _, _, _, _ = load_covers_config(hass, str(f))
        assert "cover.test" in profiles

    def test_cover_with_all_optional_fields(self, hass, tmp_path):
        cfg = {
            "cover.full": {
                "facade": "sud",
                "entity_picture": "/img/cover.png",
                "angle_left": 90.0,
                "angle_right": 90.0,
                "modes": {"Day": 40},
                "shade": {"enable": True, "distance": 0.5, "max_height": 2.0},
                "solar_gain": {"enable": False, "position_cold": 5, "position_solar": 90},
                "exclusion": [],
            }
        }
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        profiles, _, _, _, _, _ = load_covers_config(hass, str(f))
        assert "cover.full" in profiles
        p = profiles["cover.full"]
        assert p["shade"]["enable"] is True
        assert p["shade"]["distance"] == 0.5
        assert p["solar_gain"]["enable"] is False

    def test_multiple_covers_all_loaded(self, hass, tmp_path):
        cfg = {
            "cover.one": {"modes": {"Day": 40}},
            "cover.two": {"modes": {"Night": 0}},
            "not_a_cover": "should be skipped",
        }
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        profiles, _, _, _, _, _ = load_covers_config(hass, str(f))
        assert "cover.one" in profiles
        assert "cover.two" in profiles
        assert "not_a_cover" not in profiles

    def test_invalid_mode_display_skipped(self, hass, tmp_path):
        """A mode with an invalid behavior value is skipped (vol.Invalid)."""
        cfg = {"cover_extender_modes": {"Bad": {"behavior": "not_valid"}}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, modes, _, _, _, _ = load_covers_config(hass, str(f))
        assert "Bad" not in modes

    def test_invalid_cover_profile_skipped(self, hass, tmp_path):
        """A cover profile with an invalid field (angle_left: text) is skipped."""
        cfg = {"cover.bad": {"angle_left": "not_a_number"}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        profiles, _, _, _, _, _ = load_covers_config(hass, str(f))
        assert "cover.bad" not in profiles

    def test_invalid_solar_gain_global_uses_defaults(self, hass, tmp_path):
        """Invalid global solar_gain config falls back to schema defaults."""
        cfg = {"solar_gain": {"temperature_threshold": "not_a_float"}}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, _, solar, _ = load_covers_config(hass, str(f))
        assert solar["temperature_threshold"] == 19.0

    def test_non_numeric_command_interval_uses_default(self, hass, tmp_path):
        """command_interval: text → TypeError → default."""
        cfg = {"command_interval": "not_a_number"}
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump(cfg), encoding="utf-8")
        _, _, _, _, _, interval = load_covers_config(hass, str(f))
        assert interval == DEFAULT_COMMAND_INTERVAL
