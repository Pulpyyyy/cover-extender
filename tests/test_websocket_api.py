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


# ── Facades ───────────────────────────────────────────────────────────────────

def test_facades_azimuth_and_key_stripping():
    assert ws._validate_facades([{"name": "S", "azimuth": "x"}]) == "azimuth_invalid:S"
    assert ws._validate_facades([{"name": "S", "azimuth": 400}]) == "azimuth_invalid:S"
    item = {"name": "S", "azimuth": 158.4, "junk": True}
    assert ws._validate_facades([item]) is None
    assert item == {"name": "S", "azimuth": 158}  # rounded, junk dropped


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
    assert ws._flatten_template(ws._pack_template(flat)) == flat


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
