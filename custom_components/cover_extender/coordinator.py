"""CoverExtenderCoordinator — all business logic for cover_extender.

Owns the command queue, persistent memory, event listeners, and service
handlers. async_setup_entry() only instantiates this class, registers
services, and wires lifecycle hooks.

Fix #3 — worker resilience
  The queue worker catches every exception from cover service calls and logs
  it as a warning, so a bad command never kills the loop. Additionally,
  _start_worker() registers a done-callback that automatically restarts the
  worker (after a 1-second pause) if it exits for any unexpected reason.

Fix #4 — atomic map swap in _setup_profiles()
  New reverse-maps and listener subscriptions are built into local variables
  first. Only after everything is ready do we cancel the old listeners and
  replace the instance attributes in one synchronous block — eliminating the
  window where maps would be empty while new listeners are being registered.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, ServiceCall, Event, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    CONF_MODES,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
    CONF_EXCLUSION,
    ATTR_SUN_FACING,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_FACADES,
    DATA_SHOW_ENTITIES,
    DATA_SOLAR_GAIN,
    DATA_MEMORY,
    STORAGE_KEY,
    STORAGE_VERSION,
    SIGNAL_COVER_RELOAD,
    EVENT_MODE_CHANGED,
    EVENT_MEMORY_SAVED,
    EVENT_SHADE_APPLIED,
    CONF_COMMAND_INTERVAL,
    DEFAULT_COMMAND_INTERVAL,
)
from .helpers import build_extra_attrs, resolve_mode_position
from .shade import compute_sun_facing, compute_shade_sync
from .schemas import load_covers_config

_LOGGER = logging.getLogger(__name__)

# Delay before restarting the worker after an unexpected crash (seconds).
_WORKER_RESTART_DELAY = 1.0


class CoverExtenderCoordinator:
    """Encapsulates all business logic for cover_extender."""

    def __init__(self, hass: HomeAssistant, source: str) -> None:
        self.hass = hass
        self._source = source
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cover_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        # Configurable interval between cover commands (loaded from YAML)
        self._command_interval: float = DEFAULT_COMMAND_INTERVAL
        # Reverse maps rebuilt on every _setup_profiles call
        self._select_to_cover: dict[str, str] = {}
        self._lock_to_cover: dict[str, str] = {}
        self._entity_mode_map: dict[str, list[tuple[str, str]]] = {}
        # Listener unsubscribe callbacks (rebuilt on every _setup_profiles call)
        self._unsubs: list[Callable[[], None]] = []

    # ── Shortcuts to shared hass.data ─────────────────────────────────────────

    @property
    def _profiles(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN].get(DATA_COVER_PROFILES, {})

    @property
    def _modes_list(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN].get(DATA_MODES, {})

    @property
    def _facades(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN].get(DATA_FACADES, {})

    # ── Queue (Fix #3) ────────────────────────────────────────────────────────

    def _start_worker(self) -> None:
        """(Re)start the queue worker, cancelling any previous instance."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self._worker_task = self.hass.async_create_background_task(
            self._cover_queue_worker(), "cover_extender_queue_worker"
        )
        # Automatically restart the worker if it exits unexpectedly.
        self._worker_task.add_done_callback(self._on_worker_done)

    @callback
    def _on_save_done(self, task: asyncio.Task) -> None:
        """Log any error from a fire-and-forget storage save."""
        if not task.cancelled() and (exc := task.exception()):
            _LOGGER.error("cover_extender: failed to persist memory to storage: %s", exc)

    @callback
    def _on_worker_done(self, task: asyncio.Task) -> None:
        """Restart the worker after an unexpected crash (Fix #3)."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.error(
                "cover_extender: queue worker crashed (%s) — restarting in %.0fs",
                exc, _WORKER_RESTART_DELAY,
                exc_info=exc,
            )
            self.hass.loop.call_later(_WORKER_RESTART_DELAY, self._start_worker)

    async def _cover_queue_worker(self) -> None:
        """Send queued cover commands with a minimum interval between each.

        Inner try/except catches service-call failures without killing the loop.
        Outer try catches CancelledError on clean shutdown.
        """
        try:
            while True:
                service, data = await self._cover_queue.get()
                try:
                    await self.hass.services.async_call("cover", service, data)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "cover_extender: cover.%s %s failed: %s", service, data, err
                    )
                finally:
                    self._cover_queue.task_done()
                await asyncio.sleep(self._command_interval)
        except asyncio.CancelledError:
            pass

    def _enqueue_cover(self, service: str, data: dict) -> None:
        """Add a physical cover command to the global FIFO queue."""
        _LOGGER.debug("cover_extender: enqueue cover.%s %s", service, data)
        self._cover_queue.put_nowait((service, data))

    # ── Persistent memory ──────────────────────────────────────────────────────

    def _get_memory(self, entity_id: str) -> int | None:
        """Return the stored memory position for a cover, or None if not set."""
        return self.hass.data[DOMAIN].get(DATA_MEMORY, {}).get(entity_id)

    async def _set_memory(self, entity_id: str, value: int | None) -> None:
        """Store or clear a memory position and re-inject it as a cover state attribute."""
        mem = self.hass.data[DOMAIN].setdefault(DATA_MEMORY, {})
        if value is None:
            mem.pop(entity_id, None)
        else:
            mem[entity_id] = value
        state = self.hass.states.get(entity_id)
        if state:
            new_attrs = dict(state.attributes)
            if value is None:
                new_attrs.pop("memory", None)
            else:
                new_attrs["memory"] = value
            self.hass.states.async_set(entity_id, state.state, new_attrs)
        self.hass.async_create_task(self._store.async_save(dict(mem))).add_done_callback(self._on_save_done)
        self.hass.bus.async_fire(
            EVENT_MEMORY_SAVED,
            {"entity_id": entity_id, "position": value},
        )

    # ── Autonomous shade / solar gain ──────────────────────────────────────────

    @callback
    def _apply_shade(self, entity_id: str, cfg: dict[str, Any]) -> None:
        """Apply shade position when switch.<cover>_auto_shade is ON (Fix #8)."""
        cover_st = self.hass.states.get(entity_id)
        if cover_st and cover_st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("auto_shade %s: cover unavailable → skipped", entity_id)
            return
        cover_name = entity_id.split(".")[1]
        auto_sw = self.hass.states.get(f"switch.{cover_name}_auto_shade")
        if not auto_sw or auto_sw.state != "on":
            _LOGGER.debug("auto_shade %s: switch missing or off → skipped", entity_id)
            return
        position, should_update = compute_shade_sync(self.hass, entity_id, cfg)
        if not should_update:
            return
        _LOGGER.debug("auto_shade %s → %d%%", entity_id, position)
        self._enqueue_cover("set_cover_position", {"entity_id": entity_id, "position": position})
        self.hass.bus.async_fire(
            EVENT_SHADE_APPLIED,
            {"entity_id": entity_id, "position": position},
        )

    @callback
    def _apply_solar_gain(self, entity_id: str, cfg: dict[str, Any]) -> None:
        """Apply solar gain position based on temperature, sun facing, and weather (Fix #8).

        - cover unavailable    → skipped
        - switch off           → skipped
        - temp >= threshold    → no action
        - sun_facing + weather → position_solar
        - else                 → position_cold
        """
        cover_st = self.hass.states.get(entity_id)
        if cover_st and cover_st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("auto_solar_gain %s: cover unavailable → skipped", entity_id)
            return
        cover_name = entity_id.split(".")[1]
        solar_gain_sw = self.hass.states.get(f"switch.{cover_name}_auto_solar_gain")
        if not solar_gain_sw or solar_gain_sw.state != "on":
            _LOGGER.debug("auto_solar_gain %s: switch missing or off → skipped", entity_id)
            return

        solar_gain_cfg = cfg.get(CONF_SOLAR_GAIN, {})
        global_solar_gain = self.hass.data[DOMAIN].get(DATA_SOLAR_GAIN, {})

        # Temperature check
        temp_entity = global_solar_gain.get("temperature_entity")
        threshold = float(global_solar_gain.get("temperature_threshold", 19.0))
        if temp_entity:
            temp_state = self.hass.states.get(temp_entity)
            if not temp_state:
                _LOGGER.warning(
                    "auto_solar_gain %s: temperature entity '%s' not found",
                    entity_id, temp_entity,
                )
                return
            try:
                temp = float(temp_state.state)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "auto_solar_gain %s: temperature '%s' non-numeric state: %s",
                    entity_id, temp_entity, temp_state.state,
                )
                return
            if temp >= threshold:
                _LOGGER.debug(
                    "auto_solar_gain %s: temp %.1f >= threshold %.1f → no action",
                    entity_id, temp, threshold,
                )
                return

        # Sun + weather check
        sun_facing = compute_sun_facing(self.hass, cfg, self._facades)

        weather_ok = True
        weather_entity = global_solar_gain.get("weather_entity")
        good_conditions: list[str] = global_solar_gain.get("good_conditions", [])
        if weather_entity and good_conditions:
            weather_st = self.hass.states.get(weather_entity)
            if weather_st:
                weather_ok = weather_st.state in good_conditions
            else:
                _LOGGER.warning(
                    "auto_solar_gain %s: weather entity '%s' not found",
                    entity_id, weather_entity,
                )
                weather_ok = False

        position = (
            int(solar_gain_cfg.get("position_solar", 100))
            if sun_facing and weather_ok
            else int(solar_gain_cfg.get("position_cold", 0))
        )
        _LOGGER.debug(
            "auto_solar_gain %s: sun_facing=%s, weather_ok=%s → %d%%",
            entity_id, sun_facing, weather_ok, position,
        )
        self._enqueue_cover("set_cover_position", {"entity_id": entity_id, "position": position})

    # ── Mode application ───────────────────────────────────────────────────────

    async def _apply_mode_core(
        self,
        entity_id: str,
        mode: str,
        from_mode: str | None,
    ) -> None:
        """Apply a mode to a cover — internal logic.

        Does NOT update the select entity; it is already up-to-date at call time.
        """
        cfg = self._profiles.get(entity_id)
        if not cfg or mode not in cfg.get(CONF_MODES, {}):
            _LOGGER.debug("_apply_mode_core: mode '%s' not configured for %s", mode, entity_id)
            return

        cover_name = entity_id.split(".")[1]
        lock_id    = f"switch.{cover_name}_lock"
        shading_id = f"switch.{cover_name}_auto_shade"

        from_mode_cfg = self._modes_list.get(from_mode, {}) if from_mode else {}
        to_mode_cfg   = self._modes_list.get(mode, {})

        cover_state = self.hass.states.get(entity_id)
        current_pos = cover_state.attributes.get("current_position") if cover_state else None
        old_memory  = self._get_memory(entity_id)

        from_lock    = from_mode_cfg.get("lock", False)
        to_lock      = to_mode_cfg.get("lock", False)
        to_behavior = to_mode_cfg.get("behavior")  # "auto_shade", "solar_gain", or None

        # 1. unlock → lock: save current position to memory
        if not from_lock and to_lock and current_pos is not None:
            await self._set_memory(entity_id, int(current_pos))

        # 2. Apply lock switch
        await self.hass.services.async_call(
            "switch", "turn_on" if to_lock else "turn_off",
            {"entity_id": lock_id},
        )

        # 3. Apply auto_shade switch (on only if behavior == "auto_shade")
        solar_gain_id = f"switch.{cover_name}_auto_solar_gain"
        if to_behavior == "auto_shade":
            await self.hass.services.async_call("switch", "turn_on",  {"entity_id": shading_id})
            await self.hass.services.async_call("switch", "turn_on",  {"entity_id": lock_id})
        else:
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": shading_id})

        # 3b. Apply auto_solar_gain switch (on only if behavior == "solar_gain"; mutually exclusive)
        if to_behavior == "solar_gain":
            await self.hass.services.async_call("switch", "turn_on",  {"entity_id": solar_gain_id})
            await self.hass.services.async_call("switch", "turn_on",  {"entity_id": lock_id})
        else:
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": solar_gain_id})

        # 4. Position (skipped when solar_gain active — _apply_solar_gain determines position)
        target_position: int | None = None
        if to_behavior != "solar_gain":
            fixed_position = cfg.get(CONF_MODES, {}).get(mode)
            if fixed_position is not None:
                target_position = resolve_mode_position(self.hass, fixed_position)
                consume_memory  = False
            elif from_lock and not to_lock and old_memory is not None:
                target_position = old_memory
                consume_memory  = True
            else:
                _LOGGER.debug(
                    "_apply_mode_core '%s' → %s: no fixed position and no stored memory → no move",
                    mode, entity_id,
                )
                consume_memory = False

            if target_position is not None:
                exclusion: list[str] = cfg.get(CONF_EXCLUSION, [])
                if any(self.hass.states.is_state(e, "on") for e in exclusion):
                    _LOGGER.debug(
                        "_apply_mode_core '%s' → %s: exclusion active, memory ← %d%%",
                        mode, entity_id, target_position,
                    )
                    await self._set_memory(entity_id, target_position)
                else:
                    self._enqueue_cover(
                        "set_cover_position",
                        {"entity_id": entity_id, "position": target_position},
                    )
                    if consume_memory:
                        await self._set_memory(entity_id, None)

        # 5. Solar gain: compute initial position on mode entry
        if to_behavior == "solar_gain":
            self._apply_solar_gain(entity_id, cfg)

        self.hass.bus.async_fire(
            EVENT_MODE_CHANGED,
            {
                "entity_id": entity_id,
                "mode": mode,
                "from_mode": from_mode,
                "position": target_position,
            },
        )
        _LOGGER.debug(
            "_apply_mode_core '%s' → %s (from=%s, lock=%s, position=%s)",
            mode, entity_id, from_mode, to_lock, target_position,
        )

    # ── Listeners ──────────────────────────────────────────────────────────────

    @callback
    def _setup_profiles(self) -> None:
        """Register profiles and (re)create all event listeners.

        Fix #4 — atomic swap:
        New maps and listener subscriptions are built into local variables first.
        Old listeners are cancelled only once everything is ready, then the
        instance attributes are replaced in one synchronous block — there is
        never a window where the maps are empty while listeners are live.
        """
        profiles = self._profiles

        # ── Build new reverse-maps (local variables) ──────────────────────────
        new_select_to_cover: dict[str, str] = {
            f"select.mode_{eid.split('.')[1]}": eid for eid in profiles
        }
        new_lock_to_cover: dict[str, str] = {
            f"switch.{eid.split('.')[1]}_lock": eid for eid in profiles
        }
        new_entity_mode_map: dict[str, list[tuple[str, str]]] = {}
        for cover_id, cfg in profiles.items():
            for mode_name, raw_pos in cfg.get(CONF_MODES, {}).items():
                if isinstance(raw_pos, str):
                    new_entity_mode_map.setdefault(raw_pos, []).append((cover_id, mode_name))

        # ── Register new listeners (local variable) ───────────────────────────
        new_unsubs: list[Callable[[], None]] = [
            async_track_state_change_event(
                self.hass, list(profiles.keys()), self._handle_cover_state_change
            ),
            async_track_state_change_event(
                self.hass, ["sun.sun"], self._inject_sun_facing
            ),
            async_track_state_change_event(
                self.hass, list(new_select_to_cover.keys()), self._handle_select_mode_change
            ),
            async_track_state_change_event(
                self.hass, list(new_lock_to_cover.keys()), self._handle_lock_off
            ),
        ]
        if new_entity_mode_map:
            new_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    list(new_entity_mode_map.keys()),
                    self._handle_mode_entity_change,
                )
            )

        global_solar_gain = self.hass.data[DOMAIN].get(DATA_SOLAR_GAIN, {})
        solar_gain_watch: list[str] = []
        if temp_ent := global_solar_gain.get("temperature_entity"):
            solar_gain_watch.append(temp_ent)
        if weather_ent := global_solar_gain.get("weather_entity"):
            solar_gain_watch.append(weather_ent)
        if solar_gain_watch:
            new_unsubs.append(
                async_track_state_change_event(
                    self.hass, solar_gain_watch, self._handle_solar_gain_trigger
                )
            )

        # Fix #7 — trigger solar gain immediately when auto_solar_gain switch turns ON
        solar_gain_switches = [
            f"switch.{eid.split('.')[1]}_auto_solar_gain"
            for eid, cfg in profiles.items()
            if cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False)
        ]
        if solar_gain_switches:
            new_unsubs.append(
                async_track_state_change_event(
                    self.hass, solar_gain_switches, self._handle_solar_gain_switch_on
                )
            )

        # ── Atomic swap: cancel old → assign new ─────────────────────────────
        for unsub in self._unsubs:
            unsub()
        self._select_to_cover  = new_select_to_cover
        self._lock_to_cover    = new_lock_to_cover
        self._entity_mode_map  = new_entity_mode_map
        self._unsubs           = new_unsubs

        # ── Initial attribute injection on already-loaded covers ──────────────
        for entity_id, cfg in profiles.items():
            extra_attrs = build_extra_attrs(cfg, memory=self._get_memory(entity_id))
            state = self.hass.states.get(entity_id)
            if state:
                current_attrs = dict(state.attributes)
                if not all(current_attrs.get(k) == v for k, v in extra_attrs.items()):
                    self.hass.states.async_set(
                        entity_id, state.state, {**current_attrs, **extra_attrs}
                    )

        self._inject_sun_facing()

    @callback
    def _handle_cover_state_change(self, event: Event) -> None:
        """Re-inject custom attributes on every cover state change (Fix #8)."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        profiles  = self._profiles
        if not new_state or entity_id not in profiles:
            return
        # Skip attribute injection when the cover is unavailable (Fix #8)
        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        extra_attrs = build_extra_attrs(profiles[entity_id], memory=self._get_memory(entity_id))
        current_attrs = dict(new_state.attributes)
        if all(current_attrs.get(k) == v for k, v in extra_attrs.items()):
            return  # Guard against infinite loops
        self.hass.states.async_set(entity_id, new_state.state, {**current_attrs, **extra_attrs})

    @callback
    def _inject_sun_facing(self, _event: Event | None = None) -> None:
        """Recompute and inject sun_facing on all covers on each sun.sun state change (Fix #8)."""
        profiles = self._profiles
        facades  = self._facades
        for entity_id, cfg in profiles.items():
            state = self.hass.states.get(entity_id)
            # Skip unavailable covers entirely (Fix #8)
            if state and state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue

            sun_facing = compute_sun_facing(self.hass, cfg, facades)
            if sun_facing is not None and state:
                current_attrs = dict(state.attributes)
                if current_attrs.get(ATTR_SUN_FACING) != sun_facing:
                    self.hass.states.async_set(
                        entity_id, state.state,
                        {**current_attrs, ATTR_SUN_FACING: sun_facing},
                    )

            if cfg.get(CONF_SHADING, {}).get("enable", False):
                self._apply_shade(entity_id, cfg)

            if cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False):
                self._apply_solar_gain(entity_id, cfg)

    @callback
    def _handle_select_mode_change(self, event: Event) -> None:
        """Apply a mode as soon as select.mode_* changes state."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not old_state or new_state.state == old_state.state:
            return
        cover_id = self._select_to_cover.get(event.data.get("entity_id"))
        if not cover_id:
            return
        self.hass.async_create_task(
            self._apply_mode_core(cover_id, new_state.state, old_state.state)
        )

    @callback
    def _handle_lock_off(self, event: Event) -> None:
        """Apply the stored memory position when the lock is released."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not old_state:
            return
        if old_state.state != "on" or new_state.state != "off":
            return
        cover_id = self._lock_to_cover.get(event.data.get("entity_id"))
        if not cover_id:
            return
        cfg: dict = self._profiles.get(cover_id, {})
        exclusion: list[str] = cfg.get(CONF_EXCLUSION, [])
        if any(self.hass.states.is_state(e, "on") for e in exclusion):
            _LOGGER.debug("lock released %s → blocked by exclusion", cover_id)
            return
        position = self._get_memory(cover_id)
        if position is None:
            _LOGGER.debug("lock released %s → no stored memory, no move", cover_id)
            return
        _LOGGER.debug("lock released %s → applying memory %d%%", cover_id, position)
        self._enqueue_cover("set_cover_position", {"entity_id": cover_id, "position": position})
        self.hass.async_create_task(self._set_memory(cover_id, None))

    @callback
    def _handle_mode_entity_change(self, event: Event) -> None:
        """Update a cover position when its active mode's position entity changes."""
        ref_entity = event.data.get("entity_id")
        new_state  = event.data.get("new_state")
        if not new_state:
            return
        try:
            new_position = int(float(new_state.state))
        except (ValueError, TypeError):
            return
        for cover_id, mode_name in self._entity_mode_map.get(ref_entity, []):
            cover_name   = cover_id.split(".")[1]
            select_state = self.hass.states.get(f"select.mode_{cover_name}")
            if not select_state or select_state.state != mode_name:
                continue
            _LOGGER.debug(
                "mode entity '%s' → %d%% : applying to %s (mode=%s)",
                ref_entity, new_position, cover_id, mode_name,
            )
            self.hass.async_create_task(
                self._set_cover_position_impl([cover_id], new_position)
            )

    @callback
    def _handle_solar_gain_trigger(self, _event: Event | None = None) -> None:
        """Re-apply solar gain logic when temperature or weather changes."""
        for entity_id, cfg in self._profiles.items():
            if cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False):
                self._apply_solar_gain(entity_id, cfg)

    @callback
    def _handle_solar_gain_switch_on(self, event: Event) -> None:
        """Apply solar gain immediately when switch.<cover>_auto_solar_gain turns ON (Fix #7).

        Without this, the cover stays at its current position until the next
        sun.sun, temperature, or weather state change — which could be minutes away.
        """
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not old_state:
            return
        if old_state.state == "on" or new_state.state != "on":
            return  # Only react to the off → on transition
        switch_id: str = event.data.get("entity_id", "")
        # Reverse-lookup: switch.volet_sam_auto_solar_gain → cover.volet_sam
        cover_name = switch_id.removeprefix("switch.").removesuffix("_auto_solar_gain")
        cover_id   = f"cover.{cover_name}"
        cfg = self._profiles.get(cover_id)
        if cfg and cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False):
            _LOGGER.debug("solar_gain switch ON → immediate apply for %s", cover_id)
            self._apply_solar_gain(cover_id, cfg)

    # ── Service handlers ───────────────────────────────────────────────────────

    async def service_apply_mode(self, call: ServiceCall) -> dict:
        """Apply a mode to one or more covers via select.select_option."""
        mode: str       = call.data["mode"]
        target_ids: list[str] = call.data.get("entity_id", [])

        applied: list[str] = []
        skipped: list[str] = []

        for entity_id in target_ids:
            cfg = self._profiles.get(entity_id)
            if not cfg or mode not in cfg.get(CONF_MODES, {}):
                _LOGGER.debug("apply_mode: mode '%s' not configured for %s", mode, entity_id)
                skipped.append(entity_id)
                continue
            cover_name = entity_id.split(".")[1]
            select_id  = f"select.mode_{cover_name}"
            if not self.hass.states.get(select_id):
                _LOGGER.warning(
                    "apply_mode: entity '%s' not found — component not ready yet?", select_id
                )
                skipped.append(entity_id)
                continue
            await self.hass.services.async_call(
                "select", "select_option", {"entity_id": select_id, "option": mode}
            )
            applied.append(entity_id)

        return {"applied": applied, "skipped": skipped}

    async def service_get_mode_position(self, call: ServiceCall) -> dict:
        """Return the position configured for a mode on a specific cover."""
        entity_id: str = call.data["entity_id"]
        mode: str      = call.data["mode"]
        cfg = self._profiles.get(entity_id)
        if not cfg or mode not in cfg.get(CONF_MODES, {}):
            return {"position": None}
        return {"position": cfg[CONF_MODES][mode]}

    async def service_compute_shade_position(self, call: ServiceCall) -> dict:
        """Compute the solar shade position for a cover."""
        entity_id: str = call.data["entity_id"]
        cfg = self._profiles.get(entity_id, {})
        position, should_update = compute_shade_sync(self.hass, entity_id, cfg)
        _LOGGER.debug(
            "compute_shade_position %s → %d%% (update=%s)", entity_id, position, should_update
        )
        return {"position": position, "should_update": should_update}

    async def _set_cover_position_impl(self, entity_ids: list[str], position: int) -> None:
        """Move or store in memory depending on lock state."""
        for entity_id in entity_ids:
            cover_name = entity_id.split(".")[1]
            lock_state = self.hass.states.get(f"switch.{cover_name}_lock")
            if lock_state and lock_state.state == "on":
                _LOGGER.debug(
                    "set_cover_position %s: lock active → writing memory (%d%%)",
                    entity_id, position,
                )
                await self._set_memory(entity_id, position)
            else:
                self._enqueue_cover(
                    "set_cover_position", {"entity_id": entity_id, "position": position}
                )

    async def service_set_cover_position(self, call: ServiceCall) -> None:
        """Move one or more covers, respecting the lock."""
        await self._set_cover_position_impl(
            call.data.get("entity_id", []), call.data["position"]
        )

    async def service_open_cover(self, call: ServiceCall) -> None:
        """Open one or more covers (position 100), respecting the lock."""
        await self._set_cover_position_impl(call.data.get("entity_id", []), 100)

    async def service_close_cover(self, call: ServiceCall) -> None:
        """Close one or more covers (position 0), respecting the lock."""
        await self._set_cover_position_impl(call.data.get("entity_id", []), 0)

    async def service_apply_memory(self, call: ServiceCall) -> None:
        """Apply the stored memory position regardless of lock state."""
        for entity_id in call.data.get("entity_id", []):
            position = self._get_memory(entity_id)
            if position is None:
                _LOGGER.debug("apply_memory %s: no memory stored, skipping", entity_id)
                continue
            _LOGGER.debug("apply_memory %s → %d%%", entity_id, position)
            self._enqueue_cover(
                "set_cover_position", {"entity_id": entity_id, "position": position}
            )

    async def service_reload(self, call: ServiceCall) -> None:
        """Reload cover configuration from YAML without restarting HA."""
        new_profiles, new_modes_list, new_facades, new_vas, new_solar_gain, new_interval = (
            await self.hass.async_add_executor_job(load_covers_config, self.hass, self._source)
        )
        self.hass.data[DOMAIN][DATA_COVER_PROFILES]   = new_profiles
        self.hass.data[DOMAIN][DATA_MODES]            = new_modes_list
        self.hass.data[DOMAIN][DATA_FACADES]          = new_facades
        self.hass.data[DOMAIN][DATA_SHOW_ENTITIES]    = new_vas
        self.hass.data[DOMAIN][DATA_SOLAR_GAIN]       = new_solar_gain
        self.hass.data[DOMAIN][CONF_COMMAND_INTERVAL] = new_interval
        self._command_interval                        = new_interval
        self._setup_profiles()
        async_dispatcher_send(self.hass, SIGNAL_COVER_RELOAD)
        _LOGGER.info("cover_extender reloaded (%d profiles)", len(new_profiles))

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Load config, start the worker, and defer listener setup to HA started."""
        stored = await self._store.async_load() or {}
        self.hass.data[DOMAIN][DATA_MEMORY] = {k: int(v) for k, v in stored.items()}

        self._start_worker()

        profiles, modes_list, facades, show_entities, solar_gain_global, command_interval = (
            await self.hass.async_add_executor_job(load_covers_config, self.hass, self._source)
        )
        self.hass.data[DOMAIN][DATA_COVER_PROFILES]      = profiles
        self.hass.data[DOMAIN][DATA_MODES]               = modes_list
        self.hass.data[DOMAIN][DATA_FACADES]             = facades
        self.hass.data[DOMAIN][DATA_SHOW_ENTITIES]       = show_entities
        self.hass.data[DOMAIN][DATA_SOLAR_GAIN]          = solar_gain_global
        self.hass.data[DOMAIN][CONF_COMMAND_INTERVAL]    = command_interval
        self._command_interval                           = command_interval

        # _setup_profiles requires cover entities to already be in the state machine
        self.hass.bus.async_listen_once(
            "homeassistant_started", lambda _: self._setup_profiles()
        )

    async def async_stop(self, _event: Event | None = None) -> None:
        """Cancel the worker and unsubscribe all listeners."""
        if self._worker_task and not self._worker_task.done():
            # Remove done-callback before cancelling so _on_worker_done doesn't restart it.
            self._worker_task.remove_done_callback(self._on_worker_done)
            self._worker_task.cancel()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
