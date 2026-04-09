"""Tests for coordinator lifecycle: async_start, _setup_profiles, queue worker, service_reload."""
from __future__ import annotations

import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.cover_extender.coordinator import CoverExtenderCoordinator
from custom_components.cover_extender.const import (
    DOMAIN,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_FACADES,
    DATA_MEMORY,
    DATA_SOLAR_GAIN,
    DATA_SHOW_ENTITIES,
    CONF_COMMAND_INTERVAL,
    SIGNAL_COVER_RELOAD,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect

_PROFILES = {
    "cover.test": {
        "facade": "sud",
        "modes": {"Day": 40, "Sensor": "sensor.pos"},
        "shade": {"enable": False},
        "solar_gain": {"enable": False},
        "exclusion": [],
    }
}

_MODES = {
    "Day": {"lock": False, "behavior": None, "icon": "mdi:sun", "color": "orange", "hidden": False},
}


@pytest.fixture
def coord(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].update({
        DATA_COVER_PROFILES: copy.deepcopy(_PROFILES),
        DATA_MODES:          copy.deepcopy(_MODES),
        DATA_FACADES:        {"sud": {"azimuth": 180.0}},
        DATA_MEMORY:         {},
        DATA_SOLAR_GAIN:     {},
    })
    return CoverExtenderCoordinator(hass, "fake.yaml")


# ════════════════════════════════════════════════════════════════════════════
# Queue worker
# ════════════════════════════════════════════════════════════════════════════

class TestCoverQueueWorker:

    async def test_processes_enqueued_command(self, coord, hass):
        calls = []

        async def record(call):
            calls.append((call.service, dict(call.data)))

        hass.services.async_register("cover", "set_cover_position", record)
        coord._command_interval = 0
        coord._start_worker()
        coord._enqueue_cover("set_cover_position", {"entity_id": "cover.test", "position": 50})

        await coord._cover_queue.join()
        await coord.async_stop()

        assert len(calls) == 1
        assert calls[0][1]["position"] == 50

    async def test_survives_service_error(self, coord, hass):
        """Worker catches exceptions and keeps processing."""
        async def fail(call):
            raise RuntimeError("boom")

        hass.services.async_register("cover", "set_cover_position", fail)
        coord._command_interval = 0
        coord._start_worker()
        coord._enqueue_cover("set_cover_position", {"entity_id": "cover.test", "position": 50})

        await coord._cover_queue.join()
        assert not coord._worker_task.done()
        await coord.async_stop()

    async def test_processes_multiple_commands_in_order(self, coord, hass):
        positions = []

        async def record(call):
            positions.append(call.data["position"])

        hass.services.async_register("cover", "set_cover_position", record)
        coord._command_interval = 0
        coord._start_worker()

        for pos in [10, 20, 30]:
            coord._enqueue_cover("set_cover_position", {"entity_id": "cover.test", "position": pos})

        await coord._cover_queue.join()
        await coord.async_stop()

        assert positions == [10, 20, 30]

    async def test_start_worker_cancels_existing(self, coord, hass):
        """Calling _start_worker twice cancels the old task."""
        coord._command_interval = 0
        coord._start_worker()
        first_task = coord._worker_task

        coord._start_worker()
        assert first_task.cancelled() or first_task != coord._worker_task

        await coord.async_stop()


# ════════════════════════════════════════════════════════════════════════════
# _on_worker_done
# ════════════════════════════════════════════════════════════════════════════

class TestOnWorkerDone:

    def test_cancelled_task_does_not_restart(self, coord, hass):
        task = MagicMock()
        task.cancelled.return_value = True
        with patch.object(coord, "_start_worker") as mock_start:
            coord._on_worker_done(task)
            mock_start.assert_not_called()

    def test_clean_exit_does_not_restart(self, coord, hass):
        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = None
        with patch.object(coord, "_start_worker") as mock_start:
            coord._on_worker_done(task)
            mock_start.assert_not_called()

    def test_exception_schedules_restart(self, coord, hass):
        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = RuntimeError("crash")
        with patch.object(hass.loop, "call_later") as mock_later:
            coord._on_worker_done(task)
            mock_later.assert_called_once()
            # Second arg to call_later is the callback (_start_worker)
            assert mock_later.call_args[0][1] == coord._start_worker


# ════════════════════════════════════════════════════════════════════════════
# _setup_profiles
# ════════════════════════════════════════════════════════════════════════════

class TestSetupProfiles:

    def test_builds_select_to_cover_map(self, coord, hass):
        coord._setup_profiles()
        assert coord._select_to_cover.get("select.mode_test") == "cover.test"

    def test_builds_lock_to_cover_map(self, coord, hass):
        coord._setup_profiles()
        assert coord._lock_to_cover.get("switch.test_lock") == "cover.test"

    def test_registers_unsubs(self, coord, hass):
        coord._setup_profiles()
        assert len(coord._unsubs) > 0

    def test_cancels_old_unsubs(self, coord, hass):
        cancelled = []
        coord._unsubs = [lambda: cancelled.append(True)]
        coord._setup_profiles()
        assert len(cancelled) == 1

    def test_entity_mode_map_built_for_entity_id_positions(self, coord, hass):
        coord._setup_profiles()
        assert "sensor.pos" in coord._entity_mode_map
        assert ("cover.test", "Sensor") in coord._entity_mode_map["sensor.pos"]

    def test_injects_attrs_into_known_covers(self, coord, hass):
        hass.states.async_set("cover.test", "open", {"current_position": 50})
        coord._setup_profiles()
        state = hass.states.get("cover.test")
        assert "auto_shade" in state.attributes

    def test_solar_gain_watchers_registered(self, coord, hass):
        hass.data[DOMAIN][DATA_SOLAR_GAIN] = {
            "temperature_entity": "sensor.temp",
            "weather_entity": "weather.home",
        }
        unsubs_before = len(coord._unsubs)
        coord._setup_profiles()
        assert len(coord._unsubs) > unsubs_before

    def test_solar_gain_switches_registered_when_enabled(self, coord, hass):
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["solar_gain"] = {"enable": True}
        coord._setup_profiles()
        assert len(coord._unsubs) > 0

    def test_no_entity_mode_map_when_no_entity_id_positions(self, coord, hass):
        """No entity_id positions → no entity_mode_map listener (but others still registered)."""
        hass.data[DOMAIN][DATA_COVER_PROFILES]["cover.test"]["modes"] = {"Day": 40}
        coord._setup_profiles()
        assert "sensor.pos" not in coord._entity_mode_map

    def test_no_cover_state_skips_attr_injection(self, coord, hass):
        """Cover not yet in state machine → no crash."""
        coord._setup_profiles()  # cover.test has no state yet


# ════════════════════════════════════════════════════════════════════════════
# async_start
# ════════════════════════════════════════════════════════════════════════════

class TestAsyncStart:

    async def test_loads_memory_from_store(self, coord, hass):
        with patch.object(coord._store, "async_load", new_callable=AsyncMock,
                          return_value={"cover.test": 55}):
            with patch("custom_components.cover_extender.coordinator.load_covers_config",
                       return_value=({}, {}, {}, {}, {}, 0.15)):
                await coord.async_start()

        assert hass.data[DOMAIN][DATA_MEMORY]["cover.test"] == 55
        await coord.async_stop()

    async def test_starts_worker(self, coord, hass):
        with patch.object(coord._store, "async_load", new_callable=AsyncMock, return_value={}):
            with patch("custom_components.cover_extender.coordinator.load_covers_config",
                       return_value=({}, {}, {}, {}, {}, 0.15)):
                await coord.async_start()

        assert coord._worker_task is not None
        await coord.async_stop()

    async def test_populates_hass_data(self, coord, hass):
        profiles = {"cover.foo": {"modes": {}}}
        with patch.object(coord._store, "async_load", new_callable=AsyncMock, return_value={}):
            with patch("custom_components.cover_extender.coordinator.load_covers_config",
                       return_value=(profiles, {"M": {}}, {"f": {}}, {"sun_facing": True}, {}, 0.3)):
                await coord.async_start()

        assert hass.data[DOMAIN][DATA_COVER_PROFILES] == profiles
        assert coord._command_interval == 0.3
        await coord.async_stop()

    async def test_setup_profiles_called_on_homeassistant_started(self, coord, hass):
        with patch.object(coord._store, "async_load", new_callable=AsyncMock, return_value={}):
            with patch("custom_components.cover_extender.coordinator.load_covers_config",
                       return_value=({}, {}, {}, {}, {}, 0.15)):
                with patch.object(coord, "_setup_profiles") as mock_setup:
                    await coord.async_start()
                    hass.bus.async_fire("homeassistant_started", {})
                    await hass.async_block_till_done()
                    mock_setup.assert_called_once()

        await coord.async_stop()

    async def test_empty_store_uses_empty_memory(self, coord, hass):
        with patch.object(coord._store, "async_load", new_callable=AsyncMock, return_value=None):
            with patch("custom_components.cover_extender.coordinator.load_covers_config",
                       return_value=({}, {}, {}, {}, {}, 0.15)):
                await coord.async_start()

        assert hass.data[DOMAIN][DATA_MEMORY] == {}
        await coord.async_stop()


# ════════════════════════════════════════════════════════════════════════════
# service_reload
# ════════════════════════════════════════════════════════════════════════════

class TestServiceReload:

    async def test_updates_hass_data(self, coord, hass):
        new_profiles = {"cover.new": {"modes": {}}}
        with patch("custom_components.cover_extender.coordinator.load_covers_config",
                   return_value=(new_profiles, {}, {}, {}, {}, 0.5)):
            with patch.object(coord, "_setup_profiles"):
                await coord.service_reload(MagicMock())

        assert hass.data[DOMAIN][DATA_COVER_PROFILES] == new_profiles
        assert coord._command_interval == 0.5

    async def test_calls_setup_profiles(self, coord, hass):
        with patch("custom_components.cover_extender.coordinator.load_covers_config",
                   return_value=({}, {}, {}, {}, {}, 0.15)):
            with patch.object(coord, "_setup_profiles") as mock_setup:
                await coord.service_reload(MagicMock())
                mock_setup.assert_called_once()

    async def test_sends_reload_signal(self, coord, hass):
        signals = []
        async_dispatcher_connect(hass, SIGNAL_COVER_RELOAD, lambda: signals.append(True))

        with patch("custom_components.cover_extender.coordinator.load_covers_config",
                   return_value=({}, {}, {}, {}, {}, 0.15)):
            with patch.object(coord, "_setup_profiles"):
                await coord.service_reload(MagicMock())

        assert len(signals) == 1

    async def test_updates_command_interval(self, coord, hass):
        with patch("custom_components.cover_extender.coordinator.load_covers_config",
                   return_value=({}, {}, {}, {}, {}, 1.0)):
            with patch.object(coord, "_setup_profiles"):
                await coord.service_reload(MagicMock())

        assert hass.data[DOMAIN][CONF_COMMAND_INTERVAL] == 1.0
