"""Tests for the panel's server-side validation (websocket_api.py).

Since 3.0.0 this module is the ONLY writer of the configuration: everything the
panel sends passes through these validators before landing in entry.options.
The tests cover the pure validators directly and the hass-dependent ones
(covers, deletion guard, rename cascade) through the conftest fakes.
"""
from __future__ import annotations

import pytest

from custom_components.cover_extender import websocket_api as ws
from custom_components.cover_extender.const import (
    OPT_CONFIG,
    SECTION_COVER,
    SECTION_FACADE,
    SECTION_MODE,
    SECTION_TEMPLATE,
)


@pytest.fixture(autouse=True)
def _patch_registry(hass, monkeypatch):
    monkeypatch.setattr(ws.er, "async_get", lambda h: h.entity_registry)


class FakeEntry:
    def __init__(self, options):
        self.options = options


class FakeConfigEntries:
    def __init__(self, entry):
        self._entry = entry

    def async_entries(self, domain):
        return [self._entry]

    def async_update_entry(self, entry, options=None, **kwargs):
        if options is not None:
            entry.options = options


def _wire(hass, sections):
    """Give the fake hass a config entry carrying *sections*."""
    entry = FakeEntry({OPT_CONFIG: sections})
    hass.config_entries = FakeConfigEntries(entry)
    return entry


# ── Named items ───────────────────────────────────────────────────────────────

def test_named_items_require_and_dedupe_names():
    assert ws._validate_named_items([{"name": " "}]) == "name_required"
    assert ws._validate_named_items([{"name": "A"}, {"name": "A"}]) == "name_exists:A"
    items = [{"name": "  South  "}]
    assert ws._validate_named_items(items) is None
    assert items[0]["name"] == "South"  # stripped in place


# ── Modes ─────────────────────────────────────────────────────────────────────

def test_modes_behavior_and_color_validation():
    assert ws._validate_modes([{"name": "X", "behavior": "nope"}]) == "behavior_invalid:X"
    assert ws._validate_modes([{"name": "X", "color": "red"}]) == "color_invalid:X"

    item = {"name": "Shade", "behavior": "auto_shade", "color": "#ff7043"}
    assert ws._validate_modes([item]) is None
    assert item["color"] == "#FF7043"          # normalised
    assert item["lock"] is False and item["hidden"] is False  # defaults filled
    assert item["priority"] is False

    flagged = {"name": "Alarm", "priority": 1}
    assert ws._validate_modes([flagged]) is None
    assert flagged["priority"] is True


def test_modes_spares_are_cleaned():
    auto = {"name": "Auto", "spares": ["Guest", "Guest", "Gone", "Auto"]}
    guest = {"name": "Guest"}
    assert ws._validate_modes([auto, guest]) is None
    assert auto["spares"] == ["Guest"]          # no duplicate, no unknown, not itself
    assert guest["spares"] == [] and guest["fallback"] is None


def test_modes_fallback_must_be_another_existing_mode():
    assert ws._validate_modes([{"name": "Away", "fallback": "Auto"}, {"name": "Auto"}]) is None
    assert ws._validate_modes([{"name": "Away", "fallback": "Gone"}]) == "fallback_invalid:Away"
    assert ws._validate_modes([{"name": "Away", "fallback": "Away"}]) == "fallback_invalid:Away"


def test_modes_duration_validation():
    plain = {"name": "Day", "duration": 0}
    assert ws._validate_modes([plain]) is None
    assert plain["duration"] is None and plain["return_mode"] is None
    for bad in (-5, 1441, 2.5, "60", True):
        assert ws._validate_modes([{"name": "Manual", "duration": bad}]) == "duration_invalid:Manual"
    assert ws._validate_modes([{"name": "Manual", "duration": 60}]) is None


def test_giving_a_duration_to_a_return_mode_is_refused_with_a_clear_reason():
    """Pause returns to Night; later, Night is edited and given a duration."""
    pause = {"name": "Pause", "duration": 30, "return_mode": "Night"}
    night = {"name": "Night", "duration": 60}
    assert ws._validate_modes([pause, night]) == "return_mode_timed:Night:Pause"


def test_modes_return_mode_must_be_an_existing_non_timed_mode():
    day = {"name": "Day"}
    guest = {"name": "Guest", "duration": 720}
    assert ws._validate_modes([day, guest, {"name": "M", "duration": 60, "return_mode": "Day"}]) is None
    timed_target = [day, guest, {"name": "M", "duration": 60, "return_mode": "Guest"}]
    assert ws._validate_modes(timed_target) == "return_mode_timed:Guest:M"
    unknown_target = [day, {"name": "M", "duration": 60, "return_mode": "Gone"}]
    assert ws._validate_modes(unknown_target) == "return_mode_invalid:M"
    # A mode without duration keeps no return mode.
    plain = {"name": "Night", "return_mode": "Day"}
    assert ws._validate_modes([day, plain]) is None
    assert plain["return_mode"] is None


# ── Facades ───────────────────────────────────────────────────────────────────

def test_facades_azimuth_and_key_stripping():
    assert ws._validate_facades([{"name": "S", "azimuth": "x"}]) == "azimuth_invalid:S"
    assert ws._validate_facades([{"name": "S", "azimuth": 400}]) == "azimuth_invalid:S"
    item = {"name": "S", "azimuth": 158.4, "junk": True}
    assert ws._validate_facades([item]) is None
    assert item == {"name": "S", "azimuth": 158}  # rounded, junk dropped


def test_facades_tilt_stored_only_off_the_vertical():
    assert ws._validate_facades([{"name": "R", "azimuth": 0, "tilt": 95}]) == "tilt_invalid:R"
    assert ws._validate_facades([{"name": "R", "azimuth": 0, "tilt": -1}]) == "tilt_invalid:R"
    roof, wall, flat = {"name": "R", "azimuth": 0, "tilt": 29.6}, {"name": "W", "azimuth": 0, "tilt": 90},         {"name": "F", "azimuth": 180, "tilt": 0}
    assert ws._validate_facades([roof, wall, flat]) is None
    assert roof == {"name": "R", "azimuth": 0, "tilt": 30}
    assert wall == {"name": "W", "azimuth": 0}           # a wall keeps the old shape
    assert flat == {"name": "F", "azimuth": 180, "tilt": 0}


def test_angles_and_heights_reach_180():
    assert ws._coerce_behavior_number("angle_left", 200) == 180
    assert ws._coerce_behavior_number("shade_max_elevation", 150) == 150
    assert ws._BEHAVIOR_FIELDS_DEFAULTS["shade_max_elevation"] == 180


# ── Templates ─────────────────────────────────────────────────────────────────

def test_templates_pack_to_nested_storage_shape():
    items = [{"name": "Bay", "angle_left": 60, "shade_distance": 1.2}]
    assert ws._validate_templates(items) is None
    packed = items[0]
    assert packed["angle_left"] == 60
    assert packed["shade"]["distance"] == 1.2
    assert packed["shade"]["max_height"] == 1.8       # default filled in
    assert packed["solar_gain"]["position_solar"] == 100


def test_templates_cross_field_checks_and_bad_values():
    bad = [{"name": "Bay", "shade_min_height": 2.5, "shade_max_height": 1.0}]
    assert ws._validate_templates(bad) == "min_height_above_max:Bay"
    garbage = [{"name": "Bay", "angle_left": "abc"}]
    assert ws._validate_templates(garbage) == "field_invalid:angle_left"


def test_template_flatten_pack_round_trip():
    flat = {"name": "Bay", **ws._BEHAVIOR_FIELDS_DEFAULTS}
    for key in ws._ACTIVATION_FLAGS:
        flat.pop(key)
    flat["shade_distance"] = 0.9
    flat["kind"] = "wall"
    assert ws._flatten_template(ws._pack_template(flat)) == flat
    flat["kind"] = "roof"
    assert ws._flatten_template(ws._pack_template(flat)) == flat


def test_templates_kind_stored_only_off_the_wall():
    items = [{"name": "Velux", "kind": "roof"}, {"name": "Bay", "kind": "wall"}, {"name": "Old"}]
    assert ws._validate_templates(items) is None
    assert items[0]["kind"] == "roof"
    assert "kind" not in items[1] and "kind" not in items[2]   # a wall keeps the old shape
    assert ws._validate_templates([{"name": "Z", "kind": "dome"}]) == "window_kind_invalid:Z"


def test_template_and_facade_must_be_the_same_kind_of_window(hass):
    sections = {
        SECTION_FACADE: [{"name": "South", "azimuth": 180}, {"name": "Roof", "azimuth": 0, "tilt": 30}],
        SECTION_TEMPLATE: [ws._pack_template({"name": "Velux", "kind": "roof"}), ws._pack_template({"name": "Bay"})],
        SECTION_COVER: [{"entity_id": "cover.a", "facade": "Roof", "template": "Velux"},
                        {"entity_id": "cover.b", "facade": "South", "template": "Bay"}],
    }
    _wire(hass, sections)
    assert ws._kind_mismatch(hass, {}) is None
    # The cover moved to a wall with its roof template...
    moved = [dict(sections[SECTION_COVER][0], facade="South"), sections[SECTION_COVER][1]]
    assert ws._kind_mismatch(hass, {SECTION_COVER: moved}) == "window_kind_mismatch:cover.a:Velux:South"
    # ...the roof turned into a wall under it, or its template into a wall's.
    assert ws._kind_mismatch(hass, {SECTION_FACADE: [{"name": "South", "azimuth": 180}, {"name": "Roof", "azimuth": 0}]})         == "window_kind_mismatch:cover.a:Velux:Roof"
    assert ws._kind_mismatch(hass, {SECTION_TEMPLATE: [ws._pack_template({"name": "Velux"}), ws._pack_template({"name": "Bay"})]})         == "window_kind_mismatch:cover.a:Velux:Roof"


# ── Global settings ───────────────────────────────────────────────────────────

def test_global_interval_bounds_and_condition_check():
    assert ws._validate_global({"command_interval": "x"})[1] == "interval_invalid"
    assert ws._validate_global({"command_interval": 9000})[1] == "interval_invalid"
    assert ws._validate_global({"sg_good_conditions": ["volcanic"]})[1] == "condition_unknown:volcanic"


def test_global_keeps_known_keys_drops_the_rest():
    out, error = ws._validate_global({
        "command_interval": 200,
        "sg_temperature_threshold": "input_number.seuil",
        "invented_by_the_panel": True,
    })
    assert error is None
    assert out["command_interval"] == 200
    assert out["sg_temperature_threshold"] == "input_number.seuil"
    assert "invented_by_the_panel" not in out


# ── Per-cover mode configs ────────────────────────────────────────────────────

def test_mode_cfgs_shapes_and_bounds():
    names = {"Day", "Shade"}
    check = lambda cfg: ws._validate_mode_cfgs({"modes": cfg}, names)
    assert check({"Nope": {"type": "auto"}}) == "mode_unknown:Nope"
    assert check({"Day": "x"}) == "mode_cfg_invalid:Day"
    assert check({"Day": {"type": "fixed", "value": 101}}) == "position_out_of_range:Day"
    assert check({"Day": {"type": "fixed", "value": True}}) == "position_out_of_range:Day"
    assert check({"Day": {"type": "entity", "value": " "}}) == "mode_entity_required:Day"
    assert check({"Day": {"type": "teleport"}}) == "mode_cfg_invalid:Day"
    assert check({"Day": {"type": "fixed", "value": 0}}) is None


def test_mode_cfgs_accept_overrides_on_behavior_modes():
    """The 3.1.0 contract: a fixed/entity position is storable on ANY mode,
    behavior modes included - that is what a per-cover override is."""
    assert ws._validate_mode_cfgs(
        {"modes": {"Shade": {"type": "fixed", "value": 30}}}, {"Shade"}
    ) is None
    assert ws._validate_mode_cfgs(
        {"modes": {"Shade": {"type": "entity", "value": "input_number.pos"}}}, {"Shade"}
    ) is None


# ── Covers ────────────────────────────────────────────────────────────────────

def _base_sections():
    return {
        SECTION_FACADE: [{"name": "South", "azimuth": 158}],
        SECTION_MODE: [{"name": "Shade", "behavior": "auto_shade"}],
        SECTION_TEMPLATE: [ws._pack_template({"name": "Bay", "shade_distance": 1.2})],
        SECTION_COVER: [],
    }


def test_covers_identity_guards(hass):
    _wire(hass, _base_sections())
    assert ws._validate_covers(hass, [{"entity_id": " "}]) == "entity_required"
    assert ws._validate_covers(hass, [{"entity_id": "light.nope", "facade": "South"}]) \
        == "cover_domain:light.nope"
    twice = [{"entity_id": "cover.a", "facade": "South"}] * 2
    assert ws._validate_covers(hass, [dict(t) for t in twice]) == "cover_exists:cover.a"
    assert ws._validate_covers(hass, [{"entity_id": "cover.a"}]) == "facade_required:cover.a"
    assert ws._validate_covers(
        hass, [{"entity_id": "cover.a", "facade": "South", "template": "Nope"}]
    ) == "template_unknown:Nope"


def test_covers_picture_must_be_host_relative(hass):
    _wire(hass, _base_sections())
    cover = lambda pic: [{"entity_id": "cover.a", "facade": "South", "entity_picture": pic}]
    assert ws._validate_covers(hass, cover("https://x/y.png")) == "picture_invalid:cover.a"
    assert ws._validate_covers(hass, cover("//host/y.png")) == "picture_invalid:cover.a"
    ok = cover("/local/y.png")
    assert ws._validate_covers(hass, ok) is None
    assert ok[0]["entity_picture"] == "/local/y.png"


def test_covers_template_values_are_stripped_to_overrides(hass):
    _wire(hass, _base_sections())
    items = [{
        "entity_id": "cover.a", "facade": "South", "template": "Bay",
        "shade_distance": 1.2,   # same as the template → dropped
        "shade_max_height": 2.2, # real override → kept
        "shade_enable": True,    # activation flag → always kept
    }]
    assert ws._validate_covers(hass, items) is None
    assert "shade_distance" not in items[0]
    assert items[0]["shade_max_height"] == 2.2
    assert items[0]["shade_enable"] is True


def test_covers_registry_id_attached_and_cleared(hass):
    _wire(hass, _base_sections())
    hass.entity_registry.register("cover.a", "uid-a")
    items = [
        {"entity_id": "cover.a", "facade": "South"},
        {"entity_id": "cover.b", "facade": "South", "entity_registry_id": "stale"},
    ]
    assert ws._validate_covers(hass, items) is None
    assert items[0]["entity_registry_id"] == "uid-a"
    assert "entity_registry_id" not in items[1]  # unregistered → stale id dropped


# ── Deletion guard and rename cascade ─────────────────────────────────────────

def _referenced_sections():
    return {
        SECTION_FACADE: [{"name": "South", "azimuth": 158}],
        SECTION_MODE: [{"name": "Day"}, {"name": "Night"}],
        SECTION_TEMPLATE: [],
        SECTION_COVER: [{
            "entity_id": "cover.a", "facade": "South",
            "modes": {"Day": {"type": "fixed", "value": 100}},
        }],
    }


def test_rename_pair_detection():
    old = [{"name": "A"}, {"name": "B"}]
    assert ws._rename_pair(old, [{"name": "B"}, {"name": "A"}]) is None  # reorder
    assert ws._rename_pair(old, [{"name": "A"}, {"name": "C"}]) == ("B", "C")
    assert ws._rename_pair(old, [{"name": "A"}]) is None  # deletion, not rename


def test_deletion_of_referenced_mode_is_blocked(hass):
    _wire(hass, _referenced_sections())
    old = [{"name": "Day"}, {"name": "Night"}]
    error = ws._deletion_blocked(hass, "mode", old, [{"name": "Night"}])
    assert error is not None and error.startswith("in_use:Day:1:")
    # Unreferenced mode deletes freely; a rename is not a deletion.
    assert ws._deletion_blocked(hass, "mode", old, [{"name": "Day"}]) is None
    assert ws._deletion_blocked(
        hass, "mode", old, [{"name": "Sunrise"}, {"name": "Night"}]
    ) is None


def test_rename_cascades_to_covers(hass):
    _wire(hass, _referenced_sections())
    old = [{"name": "Day"}, {"name": "Night"}]
    covers = ws._renamed_covers(hass, "mode", old, [{"name": "Sunrise"}, {"name": "Night"}])
    assert covers is not None
    assert covers[0]["modes"] == {"Sunrise": {"type": "fixed", "value": 100}}
    # No rename → no rewritten covers to persist.
    assert ws._renamed_covers(hass, "mode", old, old) is None
