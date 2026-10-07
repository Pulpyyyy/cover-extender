"""Tests for the options → profiles builder (schemas.py)."""
from __future__ import annotations

import pytest

from custom_components.cover_extender import schemas
from custom_components.cover_extender.const import (
    OPT_CONFIG,
    SECTION_COVER,
    SECTION_FACADE,
    SECTION_GLOBAL,
    SECTION_MODE,
    SECTION_TEMPLATE,
)
from custom_components.cover_extender.schemas import (
    build_profiles_from_options,
    infer_template_kinds,
    lift_max_elevation,
)


class FakeEntry:
    def __init__(self, options: dict):
        self.options = options


def _entry(covers=None, facades=None, modes=None, templates=None, global_data=None) -> FakeEntry:
    sections: dict = {}
    if facades is not None:
        sections[SECTION_FACADE] = facades
    if modes is not None:
        sections[SECTION_MODE] = modes
    if templates is not None:
        sections[SECTION_TEMPLATE] = templates
    if covers is not None:
        sections[SECTION_COVER] = covers
    if global_data is not None:
        sections[SECTION_GLOBAL] = global_data
    return FakeEntry({OPT_CONFIG: sections} if sections else {})


def test_empty_entry_returns_defaults():
    profiles, modes, facades, show, sg, interval = build_profiles_from_options(_entry())
    assert profiles == {} and modes == {} and facades == {}
    assert show == {"sun_facing": False, "auto_shade": False, "solar_gain": False}
    assert interval == 0.15  # DEFAULT_COMMAND_INTERVAL_MS / 1000


def test_facades_and_modes_parsed():
    entry = _entry(
        facades=[{"name": "south", "azimuth": 175}],
        modes=[{"name": "Night", "icon": "mdi:weather-night", "lock": True, "behavior": None}],
    )
    _, modes, facades, _, _, _ = build_profiles_from_options(entry)
    assert facades == {"south": {"azimuth": 175.0, "tilt": 90.0}}  # a wall unless told otherwise
    assert modes["Night"]["lock"] is True
    assert modes["Night"]["behavior"] is None
    assert modes["Night"]["icon"] == "mdi:weather-night"
    assert modes["Night"]["color"] == "#FFFFFF"  # default
    assert modes["Night"]["hidden"] is False     # default
    assert modes["Night"]["priority"] is False   # default


def test_cover_profile_basic_and_mode_conversion():
    entry = _entry(covers=[{
        "entity_id": "cover.volet_sam",
        "facade": "south",
        "exclusion": ["binary_sensor.fenetre"],
        "inhibition": ["input_boolean.invite"],
        "modes": {
            "Day":   {"type": "fixed", "value": 100},
            "Perso": {"type": "entity", "value": " input_number.pos "},
            "Ombre": {"type": "auto"},
            "Legacy": 30,  # pre-UI numeric format
        },
    }])
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    cfg = profiles["cover.volet_sam"]
    assert cfg["facade"] == "south"
    assert cfg["exclusion"] == ["binary_sensor.fenetre"]
    assert cfg["inhibition"] == ["input_boolean.invite"]
    assert cfg["modes"]["Day"] == 100
    assert cfg["modes"]["Perso"] == "input_number.pos"  # stripped
    assert cfg["modes"]["Ombre"] is None
    assert cfg["modes"]["Legacy"] == 30


def test_template_inheritance_and_cover_override():
    entry = _entry(
        templates=[{
            "name": "grande_baie",
            "angle_left": 60,
            "angle_right": 70,
            "shade": {"distance": 1.2, "max_height": 2.4},
            "solar_gain": {"position_solar": 80},
        }],
        covers=[{
            "entity_id": "cover.volet_sam",
            "template": "grande_baie",
            "shade_enable": True,
            "shade_distance": 0.9,  # cover override beats template
        }],
    )
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    cfg = profiles["cover.volet_sam"]
    assert cfg["angle_left"] == 60.0 and cfg["angle_right"] == 70.0
    assert cfg["shade"]["enable"] is True
    assert cfg["shade"]["distance"] == 0.9          # cover override
    assert cfg["shade"]["max_height"] == 2.4        # template value
    assert cfg["shade"]["min_elevation"] == 5.0     # schema default
    assert cfg["solar_gain"]["position_solar"] == 80


def test_missing_template_falls_back_to_defaults():
    entry = _entry(covers=[{"entity_id": "cover.volet_sam", "template": "inexistant"}])
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    cfg = profiles["cover.volet_sam"]
    assert cfg["angle_left"] == 85.0
    assert cfg["shade"]["distance"] == 0.4  # SHADE_DEFAULTS


def test_global_settings_flat_keys():
    entry = _entry(global_data={
        "command_interval": 500,
        "show_sun_facing": True,
        "sg_temperature_entity": "sensor.temp_salon",
        "sg_temperature_threshold": "19.5",
        "sg_weather_entity": "weather.maison",
        "sg_good_conditions": ["sunny"],
    })
    _, _, _, show, sg, interval = build_profiles_from_options(entry)
    assert interval == 0.5
    assert show == {"sun_facing": True, "auto_shade": False, "solar_gain": False}
    assert sg["temperature_entity"] == "sensor.temp_salon"
    assert sg["temperature_threshold"] == 19.5  # numeric string coerced
    assert sg["good_conditions"] == ["sunny"]


def test_global_threshold_entity_id_stays_string():
    entry = _entry(global_data={"sg_temperature_threshold": "input_number.seuil"})
    _, _, _, _, sg, _ = build_profiles_from_options(entry)
    assert sg["temperature_threshold"] == "input_number.seuil"


def test_pre_v2_flat_options_fallback():
    """Pre-2.0 installs stored global settings as bare flat keys in entry.options."""
    entry = FakeEntry({"command_interval": 300, "show_auto_shade": True})
    _, _, _, show, _, interval = build_profiles_from_options(entry)
    assert interval == 0.3
    assert show == {"sun_facing": False, "auto_shade": True, "solar_gain": False}


def test_cover_without_entity_id_is_skipped():
    entry = _entry(covers=[{"facade": "south"}])
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    assert profiles == {}


def test_registry_id_resolves_to_current_entity_id(hass, monkeypatch):
    """A renamed cover is keyed by its CURRENT entity_id via the registry id."""
    monkeypatch.setattr(schemas.er, "async_get", lambda h: h.entity_registry)
    uid = "3f2a9c81b4de4f6e8a12c05d77e91b23"
    hass.entity_registry.register("cover.volet_salle_a_manger", uid)

    entry = _entry(covers=[{
        "entity_id": "cover.volet_sam",  # stale name from before the rename
        "entity_registry_id": uid,
        "facade": "south",
    }])

    profiles, _, _, _, _, _ = build_profiles_from_options(entry, hass)
    assert "cover.volet_salle_a_manger" in profiles
    assert "cover.volet_sam" not in profiles


def test_registry_id_unresolvable_falls_back_to_stored_entity_id(hass, monkeypatch):
    monkeypatch.setattr(schemas.er, "async_get", lambda h: h.entity_registry)
    entry = _entry(covers=[{
        "entity_id": "cover.volet_sam",
        "entity_registry_id": "unknown-uuid",
    }])

    profiles, _, _, _, _, _ = build_profiles_from_options(entry, hass)
    assert "cover.volet_sam" in profiles


def test_priority_mode_parsed():
    entry = _entry(modes=[{"name": "Alarm", "lock": True, "priority": True}])
    _, modes, _, _, _, _ = build_profiles_from_options(entry)
    assert modes["Alarm"]["priority"] is True


def test_cover_without_inhibition_gets_an_empty_list():
    entry = _entry(covers=[{"entity_id": "cover.volet_sam", "facade": "south"}])
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    assert profiles["cover.volet_sam"]["inhibition"] == []


# ── Sloped windows ────────────────────────────────────────────────────────────

def test_sloped_facade_parsed():
    entry = _entry(facades=[{"name": "Roof", "azimuth": 0, "tilt": 30}])
    _, _, facades, _, _, _ = build_profiles_from_options(entry)
    assert facades == {"Roof": {"azimuth": 0.0, "tilt": 30.0}}


def test_cover_sun_position_from_cover_then_template():
    entry = _entry(
        templates=[{"name": "Skylight", "shade": {"sun_position": 20}}],
        covers=[
            {"entity_id": "cover.a", "facade": "f", "template": "Skylight"},
            {"entity_id": "cover.b", "facade": "f", "template": "Skylight", "shade_sun_position": 45},
            {"entity_id": "cover.c", "facade": "f"},
        ],
    )
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    assert profiles["cover.a"]["shade"]["sun_position"] == 20
    assert profiles["cover.b"]["shade"]["sun_position"] == 45
    assert profiles["cover.c"]["shade"]["sun_position"] == 30   # default


def test_max_elevation_defaults_to_no_limit():
    entry = _entry(covers=[{"entity_id": "cover.a", "facade": "f"}])
    profiles, _, _, _, _, _ = build_profiles_from_options(entry)
    assert profiles["cover.a"]["shade"]["max_elevation"] == 180


def test_lift_max_elevation_turns_90_into_180_only():
    sections = {
        SECTION_TEMPLATE: [
            {"name": "A", "shade": {"max_elevation": 90, "min_elevation": 5}},
            {"name": "B", "shade": {"max_elevation": 60}},
            {"name": "C", "shade": {}},
        ],
        SECTION_COVER: [
            {"entity_id": "cover.a", "shade_max_elevation": 90.0},
            {"entity_id": "cover.b", "shade_max_elevation": 70},
            {"entity_id": "cover.c"},
        ],
        SECTION_FACADE: [{"name": "S", "azimuth": 180}],
    }
    out = lift_max_elevation(sections)
    assert [t["shade"].get("max_elevation") for t in out[SECTION_TEMPLATE]] == [180, 60, None]
    assert out[SECTION_TEMPLATE][0]["shade"]["min_elevation"] == 5
    assert [c.get("shade_max_elevation") for c in out[SECTION_COVER]] == [180, 70, None]
    assert out[SECTION_FACADE] == sections[SECTION_FACADE]
    # the input is left untouched
    assert sections[SECTION_TEMPLATE][0]["shade"]["max_elevation"] == 90


def test_lift_max_elevation_nothing_to_do():
    assert lift_max_elevation({SECTION_COVER: [{"entity_id": "cover.a", "shade_max_elevation": 45}]}) is None
    assert lift_max_elevation({}) is None


def test_infer_template_kinds_from_their_covers():
    sections = {
        SECTION_FACADE: [{"name": "S", "azimuth": 180}, {"name": "R", "azimuth": 0, "tilt": 30},
                         {"name": "F", "azimuth": 180, "tilt": 0}],
        SECTION_TEMPLATE: [{"name": "Velux"}, {"name": "Dome"}, {"name": "Mixed"}, {"name": "Bay"}, {"name": "Unused"}],
        SECTION_COVER: [
            {"entity_id": "cover.a", "facade": "R", "template": "Velux"},
            {"entity_id": "cover.b", "facade": "R", "template": "Velux"},
            {"entity_id": "cover.c", "facade": "F", "template": "Dome"},
            {"entity_id": "cover.d", "facade": "R", "template": "Mixed"},
            {"entity_id": "cover.e", "facade": "S", "template": "Mixed"},
            {"entity_id": "cover.f", "facade": "S", "template": "Bay"},
        ],
    }
    out = infer_template_kinds(sections)
    assert [t.get("kind") for t in out[SECTION_TEMPLATE]] == ["roof", "flat", None, None, None]
    assert "kind" not in sections[SECTION_TEMPLATE][0]   # the input is left untouched
    assert infer_template_kinds(out) is None              # nothing left to do
