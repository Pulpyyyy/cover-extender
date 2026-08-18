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
    assert resolve_helper_entity(hass, "cover.volet_sam", "select_mode") == "select.mode_volet_sam"
    assert resolve_helper_entity(hass, "cover.volet_sam", "auto_shade") == "switch.volet_sam_auto_shade"


def test_helper_unique_id_templates():
    assert helper_unique_id("select_mode", UID) == f"{DOMAIN}_select_mode_{UID}"
    assert helper_unique_id("lock", UID) == f"{DOMAIN}_switch_{UID}_lock"
    assert helper_unique_id("bs_sun_facing", UID) == f"{DOMAIN}_binary_sensor_{UID}_sun_facing"
