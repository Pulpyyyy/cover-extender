"""Tests for stateless helpers (helpers.py)."""
from __future__ import annotations

import pytest

from custom_components.cover_extender import helpers
from custom_components.cover_extender.const import DOMAIN
from custom_components.cover_extender.helpers import (
    build_extra_attrs,
    cover_object_id,
    cover_stable_key,
    effective_behavior,
    helper_unique_id,
    resolve_helper_entity,
    resolve_mode_position,
)


@pytest.fixture(autouse=True)
def _patch_registry(hass, monkeypatch):
    """Route er.async_get to the fake registry (works with stub AND real HA)."""
    monkeypatch.setattr(helpers.er, "async_get", lambda h: h.entity_registry)


# ── resolve_mode_position ─────────────────────────────────────────────────────

def test_resolve_mode_position_none(hass):
    assert resolve_mode_position(hass, None) is None


def test_resolve_mode_position_numeric(hass):
    assert resolve_mode_position(hass, 42) == 42
    assert resolve_mode_position(hass, 42.7) == 42


def test_resolve_mode_position_entity(hass):
    hass.states.set("input_number.pos", "37.5")
    assert resolve_mode_position(hass, "input_number.pos") == 37


def test_resolve_mode_position_entity_missing(hass):
    assert resolve_mode_position(hass, "input_number.absent") is None


def test_resolve_mode_position_entity_non_numeric(hass):
    hass.states.set("input_number.pos", "unavailable")
    assert resolve_mode_position(hass, "input_number.pos") is None


# ── effective_behavior ────────────────────────────────────────────────────────

def test_effective_behavior_no_override_keeps_behavior():
    assert effective_behavior("auto_shade", None) == "auto_shade"
    assert effective_behavior("solar_gain", None) == "solar_gain"


def test_effective_behavior_fixed_override_neutralises():
    assert effective_behavior("auto_shade", 30) is None
    assert effective_behavior("solar_gain", 0) is None  # 0 is a position, not "no value"


def test_effective_behavior_entity_override_neutralises():
    assert effective_behavior("auto_shade", "input_number.pos") is None


def test_effective_behavior_plain_mode_unaffected():
    assert effective_behavior(None, 30) is None
    assert effective_behavior(None, None) is None


# ── build_extra_attrs ─────────────────────────────────────────────────────────

def test_build_extra_attrs_minimal():
    attrs = build_extra_attrs({})
    assert attrs == {"auto_shade": False}


def test_build_extra_attrs_full():
    cfg = {
        "entity_picture": "/local/volet.png",
        "facade": "south",
        "modes": {"Day": 100, "Night": 0},
        "shade": {"enable": True},
    }
    attrs = build_extra_attrs(cfg, memory=42)
    assert attrs == {
        "entity_picture": "/local/volet.png",
        "facade": "south",
        "modes": {"Day": 100, "Night": 0},
        "auto_shade": True,
        "memory": 42,
    }


def test_build_extra_attrs_no_memory_key_when_none():
    assert "memory" not in build_extra_attrs({}, memory=None)


# ── stable key and helper resolution ─────────────────────────────────────────

UID = "3f2a9c81b4de4f6e8a12c05d77e91b23"


def test_cover_object_id():
    assert cover_object_id("cover.volet_sam") == "volet_sam"


def test_cover_stable_key_registered(hass):
    hass.entity_registry.register("cover.volet_sam", UID)
    assert cover_stable_key(hass, "cover.volet_sam") == UID


def test_cover_stable_key_unregistered_falls_back_to_object_id(hass):
    assert cover_stable_key(hass, "cover.volet_sam") == "volet_sam"


def test_resolve_helper_entity_new_scheme(hass):
    hass.entity_registry.register("cover.volet_sam", UID)
    hass.entity_registry.register_unique_id(
        "switch", DOMAIN, helper_unique_id("lock", UID), "switch.verrou_renomme"
    )
    assert resolve_helper_entity(hass, "cover.volet_sam", "lock") == "switch.verrou_renomme"


def test_resolve_helper_entity_legacy_scheme(hass):
    # Cover registered but helper still on the name-based unique_id
    hass.entity_registry.register("cover.volet_sam", UID)
    hass.entity_registry.register_unique_id(
        "switch", DOMAIN, helper_unique_id("lock", "volet_sam"), "switch.volet_sam_lock"
    )
    assert resolve_helper_entity(hass, "cover.volet_sam", "lock") == "switch.volet_sam_lock"


def test_resolve_helper_entity_conventional_fallback(hass):
    # Nothing registered yet (fresh add) → conventional name
    assert resolve_helper_entity(hass, "cover.volet_sam", "select_mode") == "select.volet_sam_cx_mode"
    assert resolve_helper_entity(hass, "cover.volet_sam", "auto_shade") == "switch.volet_sam_cx_auto_shade"


def test_helper_unique_id_templates():
    assert helper_unique_id("select_mode", UID) == f"{DOMAIN}_select_mode_{UID}"
    assert helper_unique_id("lock", UID) == f"{DOMAIN}_switch_{UID}_lock"
    assert helper_unique_id("bs_sun_facing", UID) == f"{DOMAIN}_binary_sensor_{UID}_sun_facing"


# ── 4.0 entity ids and names ──────────────────────────────────────────────────

@pytest.mark.parametrize(("kind", "expected"), [
    ("select_mode",     "select.volet_sam_cx_mode"),
    ("lock",            "switch.volet_sam_cx_lock"),
    ("auto_shade",      "switch.volet_sam_cx_auto_shade"),
    ("auto_solar_gain", "switch.volet_sam_cx_auto_solar_gain"),
    ("bs_sun_facing",   "binary_sensor.volet_sam_cx_sun_facing"),
    ("bs_auto_shade",   "binary_sensor.volet_sam_cx_auto_shade_status"),
    ("bs_solar_gain",   "binary_sensor.volet_sam_cx_solar_gain_status"),
])
def test_helper_entity_id_scheme(kind, expected):
    assert helpers.helper_entity_id(kind, "cover.volet_sam") == expected


def test_every_helper_kind_has_an_id_a_name_and_a_legacy_pattern():
    kinds = set(helpers.HELPER_UNIQUE_ID_TEMPLATES)
    assert set(helpers._HELPER_CONVENTIONAL_EIDS) == kinds
    assert set(helpers.HELPER_NAMES) == kinds
    assert set(helpers._LEGACY_EID_PATTERNS) == kinds
    # Fixed English names, all marked as coming from this integration.
    assert all(name.startswith("CX ") for name in helpers.HELPER_NAMES.values())


@pytest.mark.parametrize("kind", list(helpers.HELPER_UNIQUE_ID_TEMPLATES))
@pytest.mark.parametrize("key", [UID, "volet_sam"])
def test_helper_kind_reads_the_unique_id(kind, key):
    domain = helpers.HELPER_UNIQUE_ID_TEMPLATES[kind][0]
    assert helpers.helper_kind(domain, helper_unique_id(kind, key)) == kind


def test_helper_kind_rejects_foreign_unique_ids():
    assert helpers.helper_kind("switch", "something_else") is None
    # Right shape, wrong domain.
    assert helpers.helper_kind("select", helper_unique_id("lock", UID)) is None
    assert helpers.helper_kind("select", helpers.GLOBAL_SELECT_UNIQUE_ID) is None


@pytest.mark.parametrize(("kind", "old", "new"), [
    ("select_mode",     "select.mode_volet_sam",                "select.volet_sam_cx_mode"),
    ("lock",            "switch.volet_sam_lock",                "switch.volet_sam_cx_lock"),
    ("auto_shade",      "switch.volet_sam_auto_shade",          "switch.volet_sam_cx_auto_shade"),
    ("auto_solar_gain", "switch.volet_sam_auto_solar_gain",     "switch.volet_sam_cx_auto_solar_gain"),
    ("bs_sun_facing",   "binary_sensor.volet_sam_sun_facing",   "binary_sensor.volet_sam_cx_sun_facing"),
    ("bs_auto_shade",   "binary_sensor.volet_sam_auto_shade",   "binary_sensor.volet_sam_cx_auto_shade_status"),
    ("bs_solar_gain",   "binary_sensor.volet_sam_solar_gain",   "binary_sensor.volet_sam_cx_solar_gain_status"),
    # The cover part is kept as it is: an old cover name, a _2 from a clash.
    ("select_mode",     "select.mode_ancien_nom_2",             "select.ancien_nom_2_cx_mode"),
])
def test_v4_entity_id_renames_the_pre_4_shape(kind, old, new):
    domain = helpers.HELPER_UNIQUE_ID_TEMPLATES[kind][0]
    assert helpers.v4_entity_id(domain, helper_unique_id(kind, UID), old) == new


@pytest.mark.parametrize(("kind", "current"), [
    ("lock",          "switch.volet_sam_cx_lock"),          # already on the 4.0 scheme
    ("lock",          "switch.verrou_du_salon"),            # rewritten by the user
    ("lock",          "switch.volet_sam_lock_2"),           # not the pre-4.0 shape
    ("bs_auto_shade", "binary_sensor.volet_sam_cx_auto_shade_status"),
    ("select_mode",   "select.volet_sam_cx_mode"),
])
def test_v4_entity_id_leaves_other_ids_alone(kind, current):
    domain = helpers.HELPER_UNIQUE_ID_TEMPLATES[kind][0]
    assert helpers.v4_entity_id(domain, helper_unique_id(kind, UID), current) is None


def test_v4_entity_id_global_select():
    uid = helpers.GLOBAL_SELECT_UNIQUE_ID
    assert helpers.v4_entity_id("select", uid, "select.cover_extender_modes") == "select.cx_modes"
    assert helpers.v4_entity_id("select", uid, "select.cx_modes") is None
    assert helpers.v4_entity_id("select", uid, "select.my_modes") is None


def test_v4_entity_id_ignores_foreign_entities():
    assert helpers.v4_entity_id("switch", "other_integration_uid", "switch.kitchen_lock") is None
