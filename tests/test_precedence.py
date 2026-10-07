"""Tests for grouped requests: which modes a mode spares, and its fallback.

The example is a real configuration (the "appliquer_mode_global" script this
replaces): Automatique spares the guest, away, nap, TV and air-conditioning
modes; Nuit spares away, guests and air-conditioning; Ombre spares guests,
TV, nap, manual and air-conditioning; Absence falls back to Automatique on
covers it is not linked to.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from custom_components.cover_extender import coordinator as coord_mod
from custom_components.cover_extender.const import (
    CONF_MODES,
    DATA_COVER_PROFILES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_MODES,
    DATA_SOLAR_GAIN,
    DOMAIN,
)
from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.helpers import resolve_request

MODES = {
    "Automatique": {"spares": ["Invités", "Absence", "Sieste", "TV", "Climatisation"]},
    "Nuit":        {"spares": ["Absence", "Invités", "Climatisation"]},
    "Ombre":       {"spares": ["Invités", "TV", "Sieste", "Manuel", "Climatisation"]},
    "Absence":     {"fallback": "Automatique"},
    "Invités": {}, "Sieste": {}, "TV": {}, "Climatisation": {},
    "Manuel": {"duration": 60},
}
ALL = list(MODES)


# ── The decision (pure) ───────────────────────────────────────────────────────

@pytest.mark.parametrize("mode, current, expected", [
    ("Automatique", "Nuit",    ("Automatique", None)),
    ("Automatique", "Sieste",  ("Automatique", "spared")),
    ("Nuit",        "Sieste",  ("Nuit", None)),          # Nuit replaces a nap
    ("Nuit",        "Invités", ("Nuit", "spared")),
    ("Ombre",       "Absence", ("Ombre", None)),         # shading while away
    ("Ombre",       "Manuel",  ("Ombre", "spared")),
])
def test_spares(mode, current, expected):
    assert resolve_request(mode, ALL, current, MODES) == expected


def test_force_passes_the_spared_modes():
    assert resolve_request("Automatique", ALL, "Invités", MODES, force=True) == ("Automatique", None)


def test_fallback_on_a_cover_the_mode_is_not_linked_to():
    linked = ["Automatique", "Nuit"]
    assert resolve_request("Absence", linked, "Nuit", MODES) == ("Automatique", None)


def test_not_linked_and_no_fallback():
    assert resolve_request("Ombre", ["Automatique", "Nuit"], "Nuit", MODES) == (None, "not_linked")


def test_the_requested_modes_spares_apply_even_through_its_fallback():
    # Absence spares nothing, so its fallback applies whatever the cover is in.
    assert resolve_request("Absence", ["Automatique"], "Sieste", MODES) == ("Automatique", None)


# ── The coordinator ───────────────────────────────────────────────────────────

COVER = "cover.office"
SELECT = "select.office_cx_mode"


class FakeServices:
    def __init__(self, hass):
        self._hass = hass
        self.calls = []

    async def async_call(self, domain, service, data):
        self.calls.append((domain, service, data))
        if domain == "select":
            self._hass.states.set(data["entity_id"], data["option"])
        else:
            self._hass.states.set(data["entity_id"], "on" if service == "turn_on" else "off")


class FakeStore:
    def async_delay_save(self, *_a, **_k):
        pass


@pytest.fixture
def coord(hass, monkeypatch):
    monkeypatch.setattr(coord_mod.er, "async_get", lambda h: h.entity_registry)
    monkeypatch.setattr(coord_mod, "Store", lambda *a, **k: FakeStore())
    monkeypatch.setattr(coord_mod, "async_track_point_in_utc_time", lambda *a: (lambda: None))
    monkeypatch.setattr(coord_mod, "async_dispatcher_send", lambda *a: None)
    hass.services = FakeServices(hass)
    hass.bus = types.SimpleNamespace(async_fire=lambda *a: None)
    hass.tasks = []
    hass.async_create_task = hass.tasks.append
    c = CoverExtenderCoordinator(hass, types.SimpleNamespace())
    hass.data[DOMAIN] = {
        DATA_COVER_PROFILES: {COVER: {CONF_MODES: {m: None for m in ALL}}},
        DATA_FACADES: {}, DATA_MODES: MODES, DATA_SOLAR_GAIN: {}, DATA_MEMORY: {},
    }
    hass.states.set(SELECT, "Sieste")
    return c


def test_request_applies_through_the_selector(coord, hass):
    assert asyncio.run(coord.async_request_mode(COVER, "Nuit")) is None
    assert hass.services.calls[-1] == ("select", "select_option", {"entity_id": SELECT, "option": "Nuit"})


def test_request_spared(coord, hass):
    assert asyncio.run(coord.async_request_mode(COVER, "Automatique")) == "spared"
    assert hass.services.calls == []


def test_spared_by_a_timed_mode_becomes_its_base_mode(coord, hass):
    # The cover went Nuit → Manuel (timed): its base mode is Nuit.
    hass.states.set(SELECT, "Nuit")
    hass.states.set(SELECT, "Manuel")
    asyncio.run(coord._apply_mode_core(COVER, "Manuel", "Nuit"))
    assert coord._timers[COVER]["base"] == "Nuit"
    # Ombre spares Manuel: not applied now, but where Manuel will return.
    assert asyncio.run(coord.async_request_mode(COVER, "Ombre")) == "spared"
    assert coord._timers[COVER]["base"] == "Ombre"
    assert coord.timed_mode_info(COVER)["return_mode"] == "Ombre"


def test_global_selector_applies_to_every_cover(coord, hass):
    hass.states.set(SELECT, "Nuit")
    asyncio.run(coord.async_apply_everywhere("Ombre"))
    assert hass.states.get(SELECT).state == "Ombre"


def test_apply_mode_reports_why_a_cover_was_skipped(coord, hass):
    async def covers(_call):
        return [COVER]

    coord._extract_cover_ids = covers
    result = asyncio.run(coord.service_apply_mode(types.SimpleNamespace(data={"mode": "Automatique"})))
    assert result == {"applied": [], "skipped": [COVER], "reasons": {COVER: "spared"}}
    forced = asyncio.run(coord.service_apply_mode(
        types.SimpleNamespace(data={"mode": "Automatique", "force": True})))
    assert forced["applied"] == [COVER]
