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
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, Event, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.service import async_extract_entity_ids
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

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
    EXTERNAL_ATTRS_DATA,
    EXTERNAL_ATTRS_SIGNAL,
    EVENT_MODE_CHANGED,
    EVENT_MEMORY_SAVED,
    EVENT_SHADE_APPLIED,
    CONF_COMMAND_INTERVAL,
    DEFAULT_COMMAND_INTERVAL,
    OPT_CONFIG,
    SECTION_COVER,
)
from .helpers import (
    build_extra_attrs,
    effective_behavior,
    resolve_helper_entity,
    resolve_mode_position,
)
from .shade import compute_sun_facing, compute_shade_sync
from .schemas import build_profiles_from_options

_LOGGER = logging.getLogger(__name__)

# Delay before restarting the worker after an unexpected crash (seconds).
_WORKER_RESTART_DELAY = 1.0

# Debounce for persisting memory positions to storage (seconds). Batches the
# bursts of writes produced by rapid mode changes / multi-cover services.
_MEMORY_SAVE_DELAY = 2.0


class CoverExtenderCoordinator:
    """Encapsulates all business logic for cover_extender."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cover_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        # Configurable interval between cover commands (from the global settings)
        self._command_interval: float = DEFAULT_COMMAND_INTERVAL
        # Reverse maps rebuilt on every _setup_profiles call
        self._select_to_cover: dict[str, str] = {}
        self._lock_to_cover: dict[str, str] = {}
        self._entity_mode_map: dict[str, list[tuple[str, str]]] = {}
        # Listener unsubscribe callbacks (rebuilt on every _setup_profiles call)
        self._unsubs: list[Callable[[], None]] = []
        # Covers whose lock is being toggled off by a mode change (not a manual
        # toggle). _handle_lock_off must skip these — _apply_mode_core is the
        # single authority for memory restoration on a mode-driven unlock, since
        # it (unlike _handle_lock_off) knows the target mode's fixed position.
        self._suspend_lock_off: set[str] = set()
        # Timestamp of the last known movement per cover, used by the shade
        # time_out throttle. Stamped when we enqueue a command AND when a
        # current_position change is observed in the state machine (remote
        # controls, HA UI, other automations) — most recent write wins.
        self._last_move: dict[str, datetime] = {}
        # Reverse map switch.<cover>_auto_solar_gain → cover (rebuilt on reload)
        self._sg_switch_to_cover: dict[str, str] = {}
        # Attribute keys injected per cover — used to strip them when a cover
        # is removed from the config (otherwise they linger until restart).
        # Only tracks the direct-write (fallback) covers; reader covers carry
        # their extras through the external-attrs contract instead.
        self._injected_attrs: dict[str, set[str]] = {}
        # Reader covers whose extras we deposited into the external-attrs
        # contract — cleared (and the target re-notified) on unload.
        self._external_deposited: set[str] = set()
        # Lifecycle guards: block worker restarts / deferred setup after stop
        self._stopping: bool = False
        self._restart_handle: asyncio.TimerHandle | None = None
        self._started_unsub: Callable[[], None] | None = None
        # Entity-registry listener (renames of covers / helper entities)
        self._registry_unsub: Callable[[], None] | None = None

    # ── Data loading ──────────────────────────────────────────────────────────

    async def _load_data(
        self,
    ) -> tuple[dict, dict, dict, dict, dict, float]:
        """Load configuration from the UI-edited entry options."""
        return build_profiles_from_options(self._entry, self.hass)

    # ── Config publication / reload ───────────────────────────────────────────

    def _store_config(
        self, config: tuple[dict, dict, dict, dict, dict, float]
    ) -> None:
        """Publish a freshly built configuration tuple into hass.data."""
        profiles, modes_list, facades, show_entities, solar_gain_global, interval = config
        data = self.hass.data[DOMAIN]
        data[DATA_COVER_PROFILES]   = profiles
        data[DATA_MODES]            = modes_list
        data[DATA_FACADES]          = facades
        data[DATA_SHOW_ENTITIES]    = show_entities
        data[DATA_SOLAR_GAIN]       = solar_gain_global
        data[CONF_COMMAND_INTERVAL] = interval
        self._command_interval      = interval

    def _reload_config(self) -> int:
        """Rebuild config from entry.options, publish it, refresh listeners and entities.

        Returns the number of profiles loaded.
        """
        if self._stopping:
            return 0
        config = build_profiles_from_options(self._entry, self.hass)
        self._store_config(config)
        self._setup_profiles()
        async_dispatcher_send(self.hass, SIGNAL_COVER_RELOAD)
        return len(config[0])

    # ── Options update listener ──────────────────────────────────────────────

    async def _on_entry_updated(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Reload profiles whenever entry.options changes."""
        self._entry = entry
        count = self._reload_config()
        _LOGGER.info(
            "cover_extender: options change — reloaded %d profiles", count
        )

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
        if self._stopping:
            return
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self._worker_task = self.hass.async_create_background_task(
            self._cover_queue_worker(), "cover_extender_queue_worker"
        )
        # Automatically restart the worker if it exits unexpectedly.
        self._worker_task.add_done_callback(self._on_worker_done)

    @callback
    def _on_worker_done(self, task: asyncio.Task) -> None:
        """Restart the worker after an unexpected crash (Fix #3)."""
        if task.cancelled() or self._stopping:
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.error(
                "cover_extender: queue worker crashed (%s) — restarting in %.0fs",
                exc, _WORKER_RESTART_DELAY,
                exc_info=exc,
            )
            # Keep the handle so async_stop can cancel a pending restart.
            self._restart_handle = self.hass.loop.call_later(
                _WORKER_RESTART_DELAY, self._start_worker
            )

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
        if entity_id := data.get("entity_id"):
            self._last_move[entity_id] = dt_util.utcnow()
        self._cover_queue.put_nowait((service, data))

    # ── Persistent memory ──────────────────────────────────────────────────────
    # The memory dict is keyed by the cover's registry id (immutable) so stored
    # positions survive a rename; covers without a registry entry fall back to
    # their entity_id (pre-2.2 behaviour).

    def _memory_key(self, entity_id: str) -> str:
        """Stable storage key for a cover: registry id, else entity_id."""
        reg = er.async_get(self.hass).async_get(entity_id)
        return reg.id if reg else entity_id

    def _get_memory(self, entity_id: str) -> int | None:
        """Return the stored memory position for a cover, or None if not set."""
        return self.hass.data[DOMAIN].get(DATA_MEMORY, {}).get(self._memory_key(entity_id))

    @callback
    def _memory_to_save(self) -> dict:
        """Snapshot of the memory dict, called by the delayed storage save."""
        return dict(self.hass.data[DOMAIN].get(DATA_MEMORY, {}))

    async def _set_memory(self, entity_id: str, value: int | None) -> None:
        """Store or clear a memory position and re-inject it as a cover state attribute."""
        mem = self.hass.data[DOMAIN].setdefault(DATA_MEMORY, {})
        key = self._memory_key(entity_id)
        if value is None:
            mem.pop(key, None)
        else:
            mem[key] = value
        if self._is_reader(entity_id):
            # Reader carries "memory" itself: deposit (or drop) + notify.
            if value is None:
                self._deposit_external(entity_id, {}, drop=("memory",))
            else:
                self._deposit_external(entity_id, {"memory": value})
        else:
            state = self.hass.states.get(entity_id)
            if state:
                new_attrs = dict(state.attributes)
                if value is None:
                    new_attrs.pop("memory", None)
                else:
                    new_attrs["memory"] = value
                self.hass.states.async_set(entity_id, state.state, new_attrs)
        # Debounced write; the Store flushes pending saves on HA shutdown.
        self._store.async_delay_save(self._memory_to_save, _MEMORY_SAVE_DELAY)
        self.hass.bus.async_fire(
            EVENT_MEMORY_SAVED,
            {"entity_id": entity_id, "position": value},
        )

    # ── Exclusion ──────────────────────────────────────────────────────────────

    def _is_excluded(self, entity_id: str) -> bool:
        """True when one of the cover's exclusion entities (e.g. an open window) is on."""
        exclusion: list[str] = self._profiles.get(entity_id, {}).get(CONF_EXCLUSION, [])
        return any(self.hass.states.is_state(e, "on") for e in exclusion)

    # ── Autonomous shade / solar gain ──────────────────────────────────────────

    @callback
    def _apply_shade(self, entity_id: str, cfg: dict[str, Any]) -> None:
        """Apply shade position when switch.<cover>_auto_shade is ON (Fix #8)."""
        cover_st = self.hass.states.get(entity_id)
        if cover_st and cover_st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("auto_shade %s: cover unavailable → skipped", entity_id)
            return
        auto_sw = self.hass.states.get(
            resolve_helper_entity(self.hass, entity_id, "auto_shade")
        )
        if not auto_sw or auto_sw.state != "on":
            _LOGGER.debug("auto_shade %s: switch missing or off → skipped", entity_id)
            return
        # Nothing is memorized: the computation resumes at the next sun update
        # once the exclusion clears, and the memory keeps the pre-mode position.
        if self._is_excluded(entity_id):
            _LOGGER.debug("auto_shade %s: exclusion active → skipped", entity_id)
            return
        position, should_update = compute_shade_sync(
            self.hass, entity_id, cfg, self._last_move.get(entity_id)
        )
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
        - exclusion active     → skipped
        - temp >= threshold    → no action
        - sun_facing + weather → position_solar
        - else                 → position_cold
        """
        cover_st = self.hass.states.get(entity_id)
        if cover_st and cover_st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.debug("auto_solar_gain %s: cover unavailable → skipped", entity_id)
            return
        solar_gain_sw = self.hass.states.get(
            resolve_helper_entity(self.hass, entity_id, "auto_solar_gain")
        )
        if not solar_gain_sw or solar_gain_sw.state != "on":
            _LOGGER.debug("auto_solar_gain %s: switch missing or off → skipped", entity_id)
            return
        if self._is_excluded(entity_id):
            _LOGGER.debug("auto_solar_gain %s: exclusion active → skipped", entity_id)
            return

        solar_gain_cfg = cfg.get(CONF_SOLAR_GAIN, {})
        global_solar_gain = self.hass.data[DOMAIN].get(DATA_SOLAR_GAIN, {})

        # Temperature check
        temp_entity = global_solar_gain.get("temperature_entity")
        raw_threshold = global_solar_gain.get("temperature_threshold", 19.0)
        # threshold may be a static float OR an input_number entity id
        if isinstance(raw_threshold, str):
            th_state = self.hass.states.get(raw_threshold)
            try:
                threshold = float(th_state.state) if th_state else 19.0
            except (ValueError, TypeError):
                threshold = 19.0
        else:
            threshold = float(raw_threshold)
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
        try:
            # Own the lock-off decision for this cover: suppress _handle_lock_off
            # for any on→off transition triggered below (gather). Cleared in finally.
            self._suspend_lock_off.add(entity_id)
            cfg = self._profiles.get(entity_id)
            if not cfg or mode not in cfg.get(CONF_MODES, {}):
                _LOGGER.debug("_apply_mode_core: mode '%s' not configured for %s", mode, entity_id)
                return

            lock_id    = resolve_helper_entity(self.hass, entity_id, "lock")
            shading_id = resolve_helper_entity(self.hass, entity_id, "auto_shade")

            from_mode_cfg = self._modes_list.get(from_mode, {}) if from_mode else {}
            to_mode_cfg   = self._modes_list.get(mode, {})

            cover_state = self.hass.states.get(entity_id)
            current_pos = cover_state.attributes.get("current_position") if cover_state else None
            old_memory  = self._get_memory(entity_id)

            # "auto_shade", "solar_gain", or None - a per-cover stored position
            # overrides a computing behavior (see effective_behavior). Applied
            # to both sides so entering AND leaving an overridden mode use the
            # same semantics.
            cover_modes   = cfg.get(CONF_MODES, {})
            from_behavior = effective_behavior(
                from_mode_cfg.get("behavior"),
                cover_modes.get(from_mode) if from_mode else None,
            )
            to_behavior   = effective_behavior(
                to_mode_cfg.get("behavior"), cover_modes.get(mode)
            )
            # Effective lock: a behavior forces the lock switch on regardless of the
            # mode's own lock flag — memory save/restore must follow the same rule,
            # otherwise entering a lock=False behavior mode loses the user's position.
            from_locked = from_mode_cfg.get("lock", False) or from_behavior in ("auto_shade", "solar_gain")
            to_locked   = to_mode_cfg.get("lock", False) or to_behavior in ("auto_shade", "solar_gain")

            # 1. unlocked → locked: save current position to memory
            if not from_locked and to_locked and current_pos is not None:
                await self._set_memory(entity_id, int(current_pos))

            # 2+3+3b. Apply lock, auto_shade, and auto_solar_gain in parallel.
            # Behaviors auto_shade and solar_gain are mutually exclusive.
            solar_gain_id = resolve_helper_entity(self.hass, entity_id, "auto_solar_gain")
            switch_calls = []
            for helper_id, turn_on in (
                (lock_id, to_locked),
                (shading_id, to_behavior == "auto_shade"),
                (solar_gain_id, to_behavior == "solar_gain"),
            ):
                # auto_shade / auto_solar_gain switches only exist for covers that
                # enable them, and resolve_helper_entity still returns a conventional
                # entity_id for the others — calling a service on one of those would
                # only log "Referenced entities ... are missing" at every mode change.
                if self.hass.states.get(helper_id) is None:
                    if turn_on:
                        _LOGGER.warning(
                            "_apply_mode_core '%s' → %s: helper %s does not exist, "
                            "not applied",
                            mode, entity_id, helper_id,
                        )
                    continue
                switch_calls.append(
                    self.hass.services.async_call(
                        "switch", "turn_on" if turn_on else "turn_off",
                        {"entity_id": helper_id},
                    )
                )
            # One failed switch call must not abort the mode change mid-way
            # (position would never be applied) — log and continue instead.
            switch_results = await asyncio.gather(*switch_calls, return_exceptions=True)
            for res in switch_results:
                if isinstance(res, Exception):
                    _LOGGER.warning(
                        "_apply_mode_core '%s' → %s: switch call failed: %s",
                        mode, entity_id, res,
                    )

            # 4. Position (skipped when solar_gain active — _apply_solar_gain determines position)
            target_position: int | None = None
            if to_behavior != "solar_gain":
                fixed_position = cover_modes.get(mode)
                if fixed_position is not None:
                    target_position = resolve_mode_position(self.hass, fixed_position)
                    consume_memory  = False
                elif from_locked and not to_locked and old_memory is not None:
                    target_position = old_memory
                    consume_memory  = True
                else:
                    _LOGGER.debug(
                        "_apply_mode_core '%s' → %s: no fixed position and no stored memory → no move",
                        mode, entity_id,
                    )
                    consume_memory = False

                if target_position is not None:
                    if self._is_excluded(entity_id):
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

            # 5b. Shading: compute and apply shade position immediately on mode entry.
            #     Bypass the switch-state check in _apply_shade (the switch was just
            #     turned on above so its HA state hasn't settled yet) and the time_out
            #     throttle (last_move=None): selecting the mode is an explicit request.
            #     The exclusion is not bypassed: an open window blocks it, as it
            #     blocks every other move.
            if to_behavior == "auto_shade" and self._is_excluded(entity_id):
                _LOGGER.debug(
                    "_apply_mode_core '%s' → %s: exclusion active, shade skipped",
                    mode, entity_id,
                )
            elif to_behavior == "auto_shade":
                shade_pos, shade_should_update = compute_shade_sync(self.hass, entity_id, cfg)
                if shade_should_update:
                    self._enqueue_cover(
                        "set_cover_position", {"entity_id": entity_id, "position": shade_pos}
                    )
                    self.hass.bus.async_fire(
                        EVENT_SHADE_APPLIED, {"entity_id": entity_id, "position": shade_pos}
                    )

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
                mode, entity_id, from_mode, to_locked, target_position,
            )
        finally:
            # Re-enable manual lock-off handling for this cover.
            self._suspend_lock_off.discard(entity_id)

    # ── External attributes contract ───────────────────────────────────────────
    # A reader cover (one that declared itself in the shared contract, e.g. an
    # ESPSomfy shade) carries our extras itself. For those we deposit the extras
    # in hass.data and fire the dispatcher INSTEAD of writing the entity state,
    # which stops the ping-pong of state_changed events. Every other cover keeps
    # the direct hass.states.async_set fallback, byte-for-byte the old path.
    #
    # Init order: the target integration may load after us, so "reader" status is
    # re-checked dynamically at every injection point rather than frozen at setup.
    # A cover that starts on the fallback path and later becomes a reader is
    # migrated on its next state change: _deposit_external publishes the extras
    # and _handle_cover_state_change stops writing its state (ESPSomfy's own
    # write then drops the stale async_set attributes and re-adds them from the
    # contract). The deposit is idempotent, so a reader in steady state fires no
    # dispatcher on ordinary position steps.

    def _external_store(self) -> dict[str, Any]:
        """Return the shared external-attrs store, creating it if missing."""
        store = self.hass.data.get(EXTERNAL_ATTRS_DATA)
        if not isinstance(store, dict):
            store = {}
            self.hass.data[EXTERNAL_ATTRS_DATA] = store
        store.setdefault("readers", set())
        store.setdefault("injected", {})
        return store

    def _is_reader(self, entity_id: str) -> bool:
        """True when the cover entity can read the external-attrs contract."""
        store = self.hass.data.get(EXTERNAL_ATTRS_DATA)
        if not isinstance(store, dict):
            return False
        return entity_id in store.get("readers", ())

    def _deposit_external(
        self, entity_id: str, updates: dict[str, Any], drop: tuple[str, ...] = ()
    ) -> None:
        """Merge extras into the contract and notify the reader — only on change.

        Idempotent: when the resulting dict equals what is already stored, no
        dispatcher is fired, so steady-state position steps stay silent.
        """
        store = self._external_store()
        current = store["injected"].get(entity_id, {})
        merged = {k: v for k, v in current.items() if k not in drop}
        merged.update(updates)
        if merged == current:
            return
        store["injected"][entity_id] = merged
        self._external_deposited.add(entity_id)
        async_dispatcher_send(self.hass, EXTERNAL_ATTRS_SIGNAL, entity_id)

    def _apply_extra_attrs(
        self, entity_id: str, extra_attrs: dict[str, Any], state: Any = None
    ) -> None:
        """Carry extra_attrs on a cover, via the contract or a direct write.

        Reader   → deposit into the contract + dispatcher (no state write).
        Fallback → hass.states.async_set, exactly as before (guarded so an
                   unchanged set never fires a redundant state_changed).
        """
        if self._is_reader(entity_id):
            self._deposit_external(entity_id, extra_attrs)
            return
        if state is None:
            state = self.hass.states.get(entity_id)
        if state and not all(
            state.attributes.get(k) == v for k, v in extra_attrs.items()
        ):
            self.hass.states.async_set(
                entity_id, state.state, {**state.attributes, **extra_attrs}
            )

    def _clear_external_attrs(self) -> None:
        """Drop every extra we deposited and notify the readers (on unload).

        Only touches "injected" (our side of the contract); "readers" is owned
        by the target integration. Notifying makes the target rewrite its state
        without our extras.
        """
        store = self.hass.data.get(EXTERNAL_ATTRS_DATA)
        if not isinstance(store, dict):
            self._external_deposited.clear()
            return
        injected = store.get("injected", {})
        for entity_id in list(self._external_deposited):
            injected.pop(entity_id, None)
            async_dispatcher_send(self.hass, EXTERNAL_ATTRS_SIGNAL, entity_id)
        self._external_deposited.clear()

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
        # A stopped coordinator must never re-register listeners (a pending
        # update-listener task could still call this after async_stop during
        # the full entry reload triggered by a rename) — they would never be
        # cancelled and would duplicate commands alongside the new coordinator.
        if self._stopping:
            return
        profiles = self._profiles

        # ── Build new reverse-maps (local variables) ──────────────────────────
        # Helper entity ids are resolved through the registry so the maps stay
        # correct when the user renamed a helper entity in the UI.
        new_select_to_cover: dict[str, str] = {
            resolve_helper_entity(self.hass, eid, "select_mode"): eid for eid in profiles
        }
        new_lock_to_cover: dict[str, str] = {
            resolve_helper_entity(self.hass, eid, "lock"): eid for eid in profiles
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
        # temperature_threshold can be a static float OR an input_number entity id
        raw_thr = global_solar_gain.get("temperature_threshold", 19.0)
        if isinstance(raw_thr, str):
            solar_gain_watch.append(raw_thr)
        if weather_ent := global_solar_gain.get("weather_entity"):
            solar_gain_watch.append(weather_ent)
        if solar_gain_watch:
            new_unsubs.append(
                async_track_state_change_event(
                    self.hass, solar_gain_watch, self._handle_solar_gain_trigger
                )
            )

        # Fix #7 — trigger solar gain immediately when auto_solar_gain switch turns ON
        new_sg_switch_to_cover: dict[str, str] = {
            resolve_helper_entity(self.hass, eid, "auto_solar_gain"): eid
            for eid, cfg in profiles.items()
            if cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False)
        }
        if new_sg_switch_to_cover:
            new_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    list(new_sg_switch_to_cover.keys()),
                    self._handle_solar_gain_switch_on,
                )
            )

        # ── Atomic swap: cancel old → assign new ─────────────────────────────
        for unsub in self._unsubs:
            unsub()
        old_injected = self._injected_attrs
        self._select_to_cover     = new_select_to_cover
        self._lock_to_cover       = new_lock_to_cover
        self._entity_mode_map     = new_entity_mode_map
        self._sg_switch_to_cover  = new_sg_switch_to_cover
        self._unsubs              = new_unsubs

        # ── Strip injected attributes from covers removed from the config ─────
        # Without this they linger on the cover until the next HA restart.
        for stale_id in set(old_injected) - set(profiles):
            if stale_id in self._external_deposited:
                # Reader cover: drop our extras from the contract and let it
                # rewrite itself without them.
                self._external_store()["injected"].pop(stale_id, None)
                self._external_deposited.discard(stale_id)
                async_dispatcher_send(self.hass, EXTERNAL_ATTRS_SIGNAL, stale_id)
                continue
            state = self.hass.states.get(stale_id)
            if state:
                remaining = {
                    k: v for k, v in state.attributes.items()
                    if k not in old_injected[stale_id]
                }
                _LOGGER.debug(
                    "cover_extender: stripping injected attributes from removed cover %s",
                    stale_id,
                )
                self.hass.states.async_set(stale_id, state.state, remaining)

        # ── Initial attribute injection on already-loaded covers ──────────────
        new_injected: dict[str, set[str]] = {}
        for entity_id, cfg in profiles.items():
            extra_attrs = build_extra_attrs(cfg, memory=self._get_memory(entity_id))
            # Track every key we may inject for this cover ("memory" can appear
            # later via _set_memory, sun_facing via _inject_sun_facing). Only
            # meaningful for the fallback path; readers carry them via the
            # contract, but tracking is harmless if the cover flips over later.
            new_injected[entity_id] = set(extra_attrs) | {ATTR_SUN_FACING, "memory"}
            # Reader → contract deposit; fallback → guarded direct write.
            self._apply_extra_attrs(entity_id, extra_attrs)
        self._injected_attrs = new_injected

        self._inject_sun_facing()

    @callback
    def _handle_cover_state_change(self, event: Event) -> None:
        """Re-inject custom attributes on every cover state change (Fix #8)."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        profiles  = self._profiles
        if not new_state or entity_id not in profiles:
            return
        # Movement observed (any source: our queue, remote control, HA UI…) →
        # stamp for the shade time_out throttle. Our own attribute injections
        # never touch current_position, so they can't falsely re-arm it.
        if (
            old_state
            and (old_pos := old_state.attributes.get("current_position")) is not None
            and (new_pos := new_state.attributes.get("current_position")) is not None
            and old_pos != new_pos
        ):
            self._last_move[entity_id] = dt_util.utcnow()
        # Skip attribute injection when the cover is unavailable (Fix #8)
        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        extra_attrs = build_extra_attrs(profiles[entity_id], memory=self._get_memory(entity_id))
        # Reader → deposit (idempotent; no dispatcher on unchanged extras, so a
        # position step fires nothing) and never write the entity state.
        # Fallback → guarded direct write, exactly as before.
        self._apply_extra_attrs(entity_id, extra_attrs, new_state)

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
            if sun_facing is not None and (state or self._is_reader(entity_id)):
                # Reader → contract deposit (only on change); fallback → guarded
                # direct write (unchanged).
                self._apply_extra_attrs(
                    entity_id, {ATTR_SUN_FACING: sun_facing}, state
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
        # Mode-driven unlock: _apply_mode_core handles the position (fixed or
        # memory). Skip here to avoid a double application / spurious move.
        # One-shot consume so a later *manual* unlock still works even if
        # _apply_mode_core's cleanup is skipped for any reason.
        if cover_id in self._suspend_lock_off:
            self._suspend_lock_off.discard(cover_id)
            _LOGGER.debug("lock released %s → suspended (mode-driven), handled by _apply_mode_core", cover_id)
            return
        if self._is_excluded(cover_id):
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
            select_state = self.hass.states.get(
                resolve_helper_entity(self.hass, cover_id, "select_mode")
            )
            if not select_state or select_state.state != mode_name:
                continue
            # Respect exclusion, like _apply_mode_core and _handle_lock_off do
            if self._is_excluded(cover_id):
                _LOGGER.debug(
                    "mode entity '%s' → %s: blocked by exclusion", ref_entity, cover_id
                )
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
        cover_id = self._sg_switch_to_cover.get(switch_id)
        cfg = self._profiles.get(cover_id) if cover_id else None
        if cfg and cfg.get(CONF_SOLAR_GAIN, {}).get("enable", False):
            _LOGGER.debug("solar_gain switch ON → immediate apply for %s", cover_id)
            self._apply_solar_gain(cover_id, cfg)

    # ── Entity registry updates (renames) ─────────────────────────────────────

    @callback
    def _handle_registry_update(self, event: Event) -> None:
        """React to entity renames.

        - Tracked cover renamed → re-sync its stored entity_id in the cover
          section; the update listener then triggers a full profile reload
          keyed on the new entity_id.
        - One of our helper entities renamed → rebuild the reverse maps so the
          rename is picked up immediately (not just at the next reload).
        """
        data = event.data
        if data.get("action") != "update" or "entity_id" not in data.get("changes", {}):
            return
        old_id: str = data["changes"]["entity_id"]
        new_id: str = data["entity_id"]
        if old_id in self._profiles:
            _LOGGER.info(
                "cover_extender: cover renamed %s → %s, re-syncing config", old_id, new_id
            )
            self._sync_cover_entity_id(old_id, new_id)
            # A soft reload is not enough: the per-cover entities (select,
            # switches, sensors) keep their internal binding to the old id and
            # cannot be swapped by add/remove (same stable unique_id). A full
            # entry reload recreates everything bound to the new entity_id.
            self._schedule_entry_reload()
            return
        reg = er.async_get(self.hass).async_get(new_id)
        if reg and reg.platform == DOMAIN:
            # Helper renamed: reverse maps AND entity-to-entity subscriptions
            # (mirror binary_sensors track the switch entity_id) must rebind.
            _LOGGER.debug(
                "cover_extender: helper renamed %s → %s, reloading entry", old_id, new_id
            )
            self._schedule_entry_reload()

    def _schedule_entry_reload(self) -> None:
        """Schedule a full config-entry reload (rare events: entity renames)."""
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(self._entry.entry_id)
        )

    def _sync_cover_entity_id(self, old_id: str, new_id: str) -> None:
        """Rewrite a renamed cover's entity_id in the cover section of the options.

        async_update_entry fires the entry update listener, which reloads the
        profiles (re-resolved through the registry id anyway); if the item
        cannot be found, fall back to a direct reload.
        """
        entry = self._entry
        sections = dict(entry.options.get(OPT_CONFIG) or {})
        items = [dict(it) for it in (sections.get(SECTION_COVER) or [])]
        changed = False
        for it in items:
            if it.get("entity_id") == old_id:
                it["entity_id"] = new_id
                changed = True
        if not changed:
            self._reload_config()
            return
        self.hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, OPT_CONFIG: {**sections, SECTION_COVER: items}},
        )

    # ── Service handlers ───────────────────────────────────────────────────────

    async def _extract_cover_ids(self, call: ServiceCall) -> list[str]:
        """Resolve the service target (entity_id / device_id / area_id / label_id)
        to the cover entity ids it references."""
        entity_ids = await async_extract_entity_ids(self.hass, call)
        return sorted(e for e in entity_ids if e.startswith("cover."))

    async def service_apply_mode(self, call: ServiceCall) -> dict:
        """Apply a mode to one or more covers via select.select_option."""
        mode: str       = call.data["mode"]
        target_ids: list[str] = await self._extract_cover_ids(call)

        applied: list[str] = []
        skipped: list[str] = []

        for entity_id in target_ids:
            cfg = self._profiles.get(entity_id)
            if not cfg or mode not in cfg.get(CONF_MODES, {}):
                _LOGGER.debug("apply_mode: mode '%s' not configured for %s", mode, entity_id)
                skipped.append(entity_id)
                continue
            select_id = resolve_helper_entity(self.hass, entity_id, "select_mode")
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
        position, should_update = compute_shade_sync(
            self.hass, entity_id, cfg, self._last_move.get(entity_id)
        )
        _LOGGER.debug(
            "compute_shade_position %s → %d%% (update=%s)", entity_id, position, should_update
        )
        return {"position": position, "should_update": should_update}

    async def _set_cover_position_impl(self, entity_ids: list[str], position: int) -> None:
        """Move, or store in memory when the lock or an exclusion blocks the move."""
        for entity_id in entity_ids:
            lock_state = self.hass.states.get(
                resolve_helper_entity(self.hass, entity_id, "lock")
            )
            if lock_state and lock_state.state == "on":
                _LOGGER.debug(
                    "set_cover_position %s: lock active → writing memory (%d%%)",
                    entity_id, position,
                )
                await self._set_memory(entity_id, position)
            elif self._is_excluded(entity_id):
                _LOGGER.debug(
                    "set_cover_position %s: exclusion active → writing memory (%d%%)",
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
            await self._extract_cover_ids(call), call.data["position"]
        )

    async def service_open_cover(self, call: ServiceCall) -> None:
        """Open one or more covers (position 100), respecting the lock."""
        await self._set_cover_position_impl(await self._extract_cover_ids(call), 100)

    async def service_close_cover(self, call: ServiceCall) -> None:
        """Close one or more covers (position 0), respecting the lock."""
        await self._set_cover_position_impl(await self._extract_cover_ids(call), 0)

    async def service_apply_memory(self, call: ServiceCall) -> None:
        """Apply the stored memory position regardless of lock state."""
        for entity_id in await self._extract_cover_ids(call):
            position = self._get_memory(entity_id)
            if position is None:
                _LOGGER.debug("apply_memory %s: no memory stored, skipping", entity_id)
                continue
            _LOGGER.debug("apply_memory %s → %d%%", entity_id, position)
            self._enqueue_cover(
                "set_cover_position", {"entity_id": entity_id, "position": position}
            )

    async def service_reload(self, call: ServiceCall) -> None:
        """Reload cover configuration from entry.options without restarting HA."""
        count = self._reload_config()
        _LOGGER.info("cover_extender reloaded (%d profiles)", count)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Load config, start the worker, and defer listener setup to HA started."""
        stored = await self._store.async_load() or {}
        # Migrate legacy entity_id keys ("cover.x") to registry ids when possible
        registry = er.async_get(self.hass)
        mem: dict[str, int] = {}
        for key, val in stored.items():
            if "." in key and (reg := registry.async_get(key)):
                mem[reg.id] = int(val)
            else:
                mem[key] = int(val)
        self.hass.data[DOMAIN][DATA_MEMORY] = mem

        self._start_worker()

        self._store_config(await self._load_data())

        # React to options changes automatically
        self._entry.async_on_unload(
            self._entry.add_update_listener(self._on_entry_updated)
        )

        # React to entity renames (covers and helper entities)
        self._registry_unsub = self.hass.bus.async_listen(
            EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry_update
        )

        # _setup_profiles requires cover entities to already be in the state machine.
        # At boot, defer until HA has started; if the entry is set up/reloaded while
        # HA is already running (manual reload), run it immediately — otherwise
        # homeassistant_started never fires again and the integration stays inert.
        if self.hass.state is CoreState.running:
            self._setup_profiles()
        else:
            @callback
            def _on_ha_started(_event: Event) -> None:
                self._started_unsub = None
                self._setup_profiles()

            # Keep the unsub so async_stop cancels it if the entry is unloaded
            # before HA finishes starting (would otherwise leak listeners).
            self._started_unsub = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, _on_ha_started
            )

    async def async_stop(self, _event: Event | None = None) -> None:
        """Cancel the worker, pending restarts, and all listeners."""
        self._stopping = True
        if self._restart_handle:
            self._restart_handle.cancel()
            self._restart_handle = None
        if self._started_unsub:
            self._started_unsub()
            self._started_unsub = None
        if self._registry_unsub:
            self._registry_unsub()
            self._registry_unsub = None
        if self._worker_task and not self._worker_task.done():
            # Remove done-callback before cancelling so _on_worker_done doesn't restart it.
            self._worker_task.remove_done_callback(self._on_worker_done)
            self._worker_task.cancel()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        # Drop the extras we carried through the external-attrs contract so the
        # reader entities rewrite themselves without them.
        self._clear_external_attrs()
