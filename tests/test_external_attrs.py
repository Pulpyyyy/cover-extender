"""Tests for the external-attrs contract in the coordinator.

The coordinator imports the full Home Assistant stack, so these tests only run
where the real package is installed (CI). Locally, where conftest.py injects
stubs for a handful of HA symbols, the whole module is skipped — the pure
submodule tests (helpers, schemas, shade) still run.

The coordinator is instantiated against the lightweight FakeHass from
conftest.py; Store and the dispatcher are patched out, and the entity registry
is routed to the fake one — the same technique test_helpers.py already uses.
"""
from __future__ import annotations

import types

import pytest

# Real HA only: the stub conftest never provides homeassistant.config_entries.
pytest.importorskip("homeassistant.config_entries")

from custom_components.cover_extender import coordinator as coord_mod
from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_MEMORY,
    CONF_MODES,
    EXTERNAL_ATTRS_DATA,
    EXTERNAL_ATTRS_SIGNAL,
)

from .conftest import FakeState


class FakeEvent:
    """Minimal stand-in for a state_changed Event."""

    def __init__(self, data: dict):
        self.data = data


def _state_change_event(entity_id: str, old_pos: int, new_pos: int) -> FakeEvent:
    return FakeEvent(
        {
            "entity_id": entity_id,
            "old_state": FakeState("open", {"current_position": old_pos}),
            "new_state": FakeState("open", {"current_position": new_pos}),
        }
    )


@pytest.fixture
def coord(hass, monkeypatch):
    """A coordinator wired to the fake hass, with Store/dispatcher patched out."""
    monkeypatch.setattr(coord_mod.er, "async_get", lambda h: h.entity_registry)
    monkeypatch.setattr(coord_mod, "Store", lambda *a, **k: object())
    sends: list[tuple] = []
    monkeypatch.setattr(
        coord_mod, "async_dispatcher_send",
        lambda h, signal, *args: sends.append((signal, args)),
    )
    c = CoverExtenderCoordinator(hass, types.SimpleNamespace())
    hass.data[DOMAIN] = {DATA_COVER_PROFILES: {}, DATA_MEMORY: {}}
    c._sends = sends  # type: ignore[attr-defined]
    return c


def _set_contract(hass, readers=(), injected=None):
    hass.data[EXTERNAL_ATTRS_DATA] = {
        "readers": set(readers),
        "injected": dict(injected or {}),
    }


# ── _is_reader (dynamic) ──────────────────────────────────────────────────────

def test_is_reader_dynamic(coord, hass):
    # No contract at all → not a reader (soft).
    assert coord._is_reader("cover.x") is False
    _set_contract(hass, readers={"cover.x"})
    assert coord._is_reader("cover.x") is True
    assert coord._is_reader("cover.y") is False


# ── _deposit_external (idempotent + drop) ─────────────────────────────────────

def test_deposit_external_change_drop_and_idempotency(coord, hass):
    _set_contract(hass, readers={"cover.s"})
    coord._deposit_external("cover.s", {"memory": 42})
    assert hass.data[EXTERNAL_ATTRS_DATA]["injected"]["cover.s"] == {"memory": 42}
    # Dropping the key removes it and notifies again.
    coord._deposit_external("cover.s", {}, drop=("memory",))
    assert hass.data[EXTERNAL_ATTRS_DATA]["injected"]["cover.s"] == {}
    assert len(coord._sends) == 2
    # No change → no dispatcher.
    coord._deposit_external("cover.s", {}, drop=("memory",))
    assert len(coord._sends) == 2


# ── _handle_cover_state_change: reader vs fallback ────────────────────────────

def test_non_reader_falls_back_to_async_set(coord, hass):
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.velux": {CONF_MODES: {"Day": 100}}}
    _set_contract(hass)  # readers empty
    hass.states.set("cover.velux", "open", {"current_position": 50})

    coord._handle_cover_state_change(_state_change_event("cover.velux", 50, 50))

    st = hass.states.get("cover.velux")
    assert st.attributes.get("modes") == {"Day": 100}
    assert st.attributes.get("auto_shade") is False
    # Nothing went through the contract.
    assert hass.data[EXTERNAL_ATTRS_DATA]["injected"] == {}
    assert coord._sends == []


def test_reader_deposits_and_does_not_write_state(coord, hass):
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.somfy": {CONF_MODES: {"Day": 100}}}
    _set_contract(hass, readers={"cover.somfy"})
    hass.states.set("cover.somfy", "open", {"current_position": 40})

    coord._handle_cover_state_change(_state_change_event("cover.somfy", 30, 40))

    injected = hass.data[EXTERNAL_ATTRS_DATA]["injected"]
    assert injected["cover.somfy"]["modes"] == {"Day": 100}
    assert injected["cover.somfy"]["auto_shade"] is False
    assert coord._sends == [(EXTERNAL_ATTRS_SIGNAL, ("cover.somfy",))]
    # The entity state was NOT rewritten with the extras (no ping-pong).
    assert "modes" not in hass.states.get("cover.somfy").attributes
    # Movement is still stamped for the shade throttle.
    assert "cover.somfy" in coord._last_move


def test_reader_position_steps_are_silent(coord, hass):
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.somfy": {CONF_MODES: {"Day": 100}}}
    _set_contract(hass, readers={"cover.somfy"})
    hass.states.set("cover.somfy", "open", {"current_position": 40})

    coord._handle_cover_state_change(_state_change_event("cover.somfy", 30, 40))
    coord._handle_cover_state_change(_state_change_event("cover.somfy", 40, 55))
    coord._handle_cover_state_change(_state_change_event("cover.somfy", 55, 70))

    # Extras never change on a position step → a single dispatcher, ever.
    assert len(coord._sends) == 1


def test_cover_migrates_from_fallback_to_reader(coord, hass):
    hass.data[DOMAIN][DATA_COVER_PROFILES] = {"cover.somfy": {CONF_MODES: {"Day": 100}}}
    _set_contract(hass)  # not a reader yet (target integration not loaded)
    hass.states.set("cover.somfy", "open", {"current_position": 40})

    coord._handle_cover_state_change(_state_change_event("cover.somfy", 30, 40))
    # Fallback path took effect.
    assert "modes" in hass.states.get("cover.somfy").attributes
    assert coord._sends == []

    # Target integration comes up and registers the cover as a reader.
    hass.data[EXTERNAL_ATTRS_DATA]["readers"].add("cover.somfy")
    coord._handle_cover_state_change(_state_change_event("cover.somfy", 40, 55))

    assert hass.data[EXTERNAL_ATTRS_DATA]["injected"]["cover.somfy"]["modes"] == {"Day": 100}
    assert coord._sends == [(EXTERNAL_ATTRS_SIGNAL, ("cover.somfy",))]


# ── _apply_extra_attrs (used by sun_facing / setup injection) ─────────────────

def test_apply_extra_attrs_reader_vs_fallback(coord, hass):
    _set_contract(hass, readers={"cover.reader"})
    coord._apply_extra_attrs("cover.reader", {"sun_facing": True})
    assert hass.data[EXTERNAL_ATTRS_DATA]["injected"]["cover.reader"] == {"sun_facing": True}

    hass.states.set("cover.plain", "open", {})
    coord._apply_extra_attrs("cover.plain", {"sun_facing": False})
    assert hass.states.get("cover.plain").attributes == {"sun_facing": False}


# ── unload cleanup ────────────────────────────────────────────────────────────

def test_clear_external_attrs_removes_injected_keeps_readers(coord, hass):
    _set_contract(
        hass, readers={"cover.somfy"}, injected={"cover.somfy": {"facade": "south"}}
    )
    coord._external_deposited = {"cover.somfy"}

    coord._clear_external_attrs()

    assert hass.data[EXTERNAL_ATTRS_DATA]["injected"] == {}
    # readers is owned by the target integration — never touched.
    assert hass.data[EXTERNAL_ATTRS_DATA]["readers"] == {"cover.somfy"}
    assert coord._sends == [(EXTERNAL_ATTRS_SIGNAL, ("cover.somfy",))]
    assert coord._external_deposited == set()
