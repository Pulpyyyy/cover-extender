"""
Cover Extender — enriches existing cover entities without creating new ones.

Injects custom attributes (entity_picture, facade, modes, enable_auto_shade, sun_facing)
and auto-creates the following helper entities for each configured cover:
  - select.mode_<cover>          mode selector
  - switch.<cover>_lock          automation lock
  - switch.<cover>_auto_shade  autonomous solar shading (shade.enable: true only)

Configuration in configuration.yaml:
  cover_extender:
    source: yaml_entities/covers_config.yaml

Command throttling:
  All physical cover commands (cover.set_cover_position, open_cover, close_cover) are
  routed through a single global FIFO queue processed by a background worker. The worker
  enforces a minimum 150 ms interval between two consecutive commands to avoid overwhelming
  the shared RF/bus controller. Non-physical commands (switch lock/auto_shade) bypass the
  queue and are sent immediately.

Architecture:
  All business logic is encapsulated in CoverExtenderCoordinator. async_setup_entry()
  instantiates the coordinator, registers services, and forwards platform setup.
  async_setup() only triggers the import flow for backward-compatible YAML configuration.
  The coordinator is stored in hass.data[DOMAIN]["coordinator"] and exposes its state
  (profiles, modes, facades) in hass.data[DOMAIN] for the select/switch sub-platforms.

Autonomous shade:
  When switch.<cover>_auto_shade is ON, cover_extender computes and applies the shade
  position on every sun.sun state change — no blueprint required.
  The switch is turned on/off by apply_mode when entering/leaving a mode with auto_shade: true.
  The automation lock (switch.<cover>_lock) is activated together with auto_shade
  so that the blueprint ignores memory/lock triggers while shade is active.

  Shading parameters (shade: block in the cover YAML config):
    distance          (optional, default: 0.3)   obstacle depth in metres
    max_height        (optional, default: 1.5)   shutter max height in metres
    min_height        (optional, default: 0.0)   shutter min height in metres
    degrees           (optional, default: 90)    solar cone half-angle (degrees)
    max_elevation     (optional, default: 90)    max sun elevation considered (degrees)
    min_elevation     (optional, default: 5)     min sun elevation considered (degrees)
    minimum_position  (optional, default: 10)    position floor when sun is in FOV (%)
    default_position  (optional, default: 100)   position when sun is outside FOV (%)
    change_threshold  (optional, default: 5)     min diff to trigger a move — if the
                                                 computed position is within this range of
                                                 the current position, it is snapped to
                                                 the current value and no move is issued
    time_out          (optional, default: 1)     min delay between two moves (minutes)

Available services:
  - cover_extender.apply_mode(mode, entity_id)         apply a mode to one or more covers
  - cover_extender.compute_shade_position(entity_id)   compute solar shade position
  - cover_extender.get_mode_position(entity_id, mode)  return the position set for a mode
  - cover_extender.reload                              reload YAML config without restarting HA
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import timedelta
from collections.abc import Callable
from typing import Any

import voluptuous as vol
import yaml

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant, ServiceCall, Event, callback, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_FACADE,
    CONF_MODES,
    CONF_MODES_SECTION,
    CONF_ENTITY_PICTURE,
    CONF_SHADING,
    CONF_SOLAR_GAIN,
    CONF_VALUE_AS_SENSOR,
    ATTR_FACADE,
    ATTR_MODES,
    ATTR_ENABLE_AUTO_SHADE,
    ATTR_SOLEIL_EN_FACE,
    CONF_ANGLE_LEFT,
    CONF_ANGLE_RIGHT,
    CONF_EXCLUSION,
    CONF_FACADES,
    CONF_AZIMUTH,
    SERVICE_APPLY_MODE,
    SERVICE_RELOAD,
    SERVICE_GET_MODE_POSITION,
    SERVICE_COMPUTE_SHADE_POSITION,
    SERVICE_SET_COVER_POSITION,
    SERVICE_OPEN_COVER,
    SERVICE_CLOSE_COVER,
    SERVICE_APPLY_MEMORY,
    DATA_COVER_PROFILES,
    DATA_MODES,
    DATA_FACADES,
    DATA_VALUE_AS_SENSOR,
    DATA_SOLAR_GAIN,
    DATA_MEMORY,
    STORAGE_KEY,
    STORAGE_VERSION,
    SIGNAL_COVER_RELOAD,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["select", "switch", "binary_sensor"]

# ── Pure helpers (no hass state, fully testable) ──────────────────────────────

def _compute_facade_lit(
    hass: HomeAssistant,
    facade_name: str,
    facades_cfg: dict[str, Any],
    angle_left: float = 85.0,
    angle_right: float = 85.0,
) -> bool | None:
    """Return True if the sun illuminates the given facade, False if not, None if sun.sun is unavailable."""
    sun_st = hass.states.get("sun.sun")
    if not sun_st:
        return None

    elevation = float(sun_st.attributes.get("elevation", 0))
    if elevation < 3:
        return False

    azimuth = float(sun_st.attributes.get("azimuth", 0))
    axe = float(facades_cfg.get(facade_name, {}).get(CONF_AZIMUTH, 180.0))

    min_az = (axe - angle_left)  % 360
    max_az = (axe + angle_right) % 360

    if min_az < max_az:
        return min_az <= azimuth <= max_az
    return azimuth >= min_az or azimuth <= max_az


def _compute_sun_facing(
    hass: HomeAssistant,
    cfg: dict[str, Any],
    facades_cfg: dict[str, Any],
) -> bool | None:
    """Return True if the sun is facing the cover (per-cover angles, per-facade azimuth)."""
    facade = cfg.get(CONF_FACADE)
    if not facade:
        return None
    return _compute_facade_lit(
        hass, facade, facades_cfg,
        angle_left=float(cfg.get(CONF_ANGLE_LEFT,  85.0)),
        angle_right=float(cfg.get(CONF_ANGLE_RIGHT, 85.0)),
    )


def _compute_shade_sync(
    hass: HomeAssistant,
    entity_id: str,
    cfg: dict[str, Any],
) -> tuple[int, bool]:
    """Compute the shade position and should_update flag (synchronous).

    Applies the change_threshold: if the difference between the computed position
    and the current position is below the threshold, the current position is
    returned unchanged and should_update is False.
    """
    auto_shade = cfg.get(CONF_SHADING, {})

    distance      = float(auto_shade.get("distance",          0.3))
    h_max         = float(auto_shade.get("max_height",        1.5))
    h_min         = float(auto_shade.get("min_height",        0.0))
    degrees       = float(auto_shade.get("degrees",           90))
    max_elev      = float(auto_shade.get("max_elevation",     90))
    min_elev      = float(auto_shade.get("min_elevation",     5))
    min_pos       = float(auto_shade.get("minimum_position",  10))
    threshold     = float(auto_shade.get("change_threshold",  5))
    time_out      = float(auto_shade.get("time_out",          1))

    modes_dict  = cfg.get(CONF_MODES, {})
    ombre_fixed = modes_dict.get("Ombre")
    default_pos = float(ombre_fixed) if ombre_fixed is not None else float(auto_shade.get("default_position", 100))

    facade      = cfg.get(CONF_FACADE, "sud")
    facades_cfg = hass.data[DOMAIN].get(DATA_FACADES, {})
    win_azi     = float(facades_cfg.get(facade, {}).get(CONF_AZIMUTH, 180.0))

    sun_st = hass.states.get("sun.sun")
    if not sun_st:
        return int(default_pos), False
    sun_azi = float(sun_st.attributes.get("azimuth",   180))
    sun_ele = float(sun_st.attributes.get("elevation", 0))

    deg2rad = math.pi / 180
    fov     = deg2rad * degrees
    alpha   = deg2rad * sun_ele
    gamma   = deg2rad * ((win_azi - sun_azi + 180) % 360 - 180)
    default_height_m = default_pos / 100.0 * h_max

    def _h2perc(h: float) -> float:
        return 100.0 * (h - h_min) / (h_max - h_min) if h_max != h_min else 0.0

    def _clip(x: float, lo: float, hi: float) -> float:
        return max(min(x, hi), lo)

    in_fov = (-fov <= gamma <= fov) and (deg2rad * min_elev <= alpha <= deg2rad * max_elev)
    if not in_fov:
        position = int(_clip(round(_h2perc(default_height_m)), 0, 100))
        _LOGGER.debug(
            "shade %s: sun outside FOV (azi_diff=%.1f°, elev=%.1f°) → default position %d%%",
            entity_id, math.degrees(gamma), math.degrees(alpha), position,
        )
    else:
        try:
            h = (distance / math.cos(gamma)) * math.tan(alpha)
        except ZeroDivisionError:
            h = default_height_m
        position = int(_clip(round(_h2perc(h)), min_pos, 100))
        _LOGGER.debug(
            "shade %s: sun inside FOV (azi_diff=%.1f°, elev=%.1f°) → computed position %d%%",
            entity_id, math.degrees(gamma), math.degrees(alpha), position,
        )

    cover_st = hass.states.get(entity_id)
    if cover_st:
        current = int(cover_st.attributes.get("current_position", position))
        diff = abs(current - position)
        if diff < threshold:
            _LOGGER.debug(
                "shade %s: diff %d%% below threshold %d%% → no move",
                entity_id, diff, threshold,
            )
            position = current
            should_update = False
        else:
            time_ok = dt_util.utcnow() - timedelta(minutes=time_out) >= cover_st.last_updated
            if not time_ok:
                _LOGGER.debug(
                    "shade %s: time_out %.1f min not elapsed → no move",
                    entity_id, time_out,
                )
            should_update = time_ok
    else:
        should_update = True

    return position, should_update


def _resolve_mode_position(hass: HomeAssistant, raw: Any) -> int | None:
    """Resolve a mode position: direct integer or a HA entity state.

    - raw = None  → None (no fixed position, e.g. auto shade)
    - raw = int   → returned as-is
    - raw = str   → interpreted as entity_id; its numeric state is read at runtime
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        state = hass.states.get(raw)
        if state is None:
            _LOGGER.warning("cover_extender: position entity '%s' not found", raw)
            return None
        try:
            return int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "cover_extender: position entity '%s' has a non-numeric state: %s",
                raw, state.state,
            )
            return None
    return int(raw)


def _build_extra_attrs(cfg: dict[str, Any], memory: int | None = None) -> dict[str, Any]:
    """Build the dict of extra attributes to inject into a cover entity."""
    attrs: dict[str, Any] = {}
    if entity_picture := cfg.get(CONF_ENTITY_PICTURE):
        attrs["entity_picture"] = entity_picture
    if facade := cfg.get(CONF_FACADE):
        attrs[ATTR_FACADE] = facade
    if modes := cfg.get(CONF_MODES):
        attrs[ATTR_MODES] = dict(modes)
    attrs[ATTR_ENABLE_AUTO_SHADE] = bool(cfg.get(CONF_SHADING, {}).get("enable", False))
    if memory is not None:
        attrs["memory"] = memory
    return attrs


def _load_covers_config(hass: HomeAssistant, source: str) -> dict[str, Any]:
    """Load cover configuration from a YAML file."""
    if not os.path.isabs(source):
        source = hass.config.path(source)

    try:
        with open(source, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _LOGGER.error("Cover config file not found: %s", source)
        return {}, {}, {}, {}
    except yaml.YAMLError as err:
        _LOGGER.error("YAML error in %s: %s", source, err)
        return {}, {}, {}, {}

    # ── Validate and normalise facades ───────────────────────────────────────
    raw_facades: dict = raw.get(CONF_FACADES, {})
    facades: dict = {}
    for name, fcfg in raw_facades.items():
        try:
            facades[name] = _FACADE_SCHEMA(fcfg or {})
        except vol.Invalid as err:
            _LOGGER.warning("Cover config: invalid facade '%s': %s", name, err)

    # ── Validate and normalise cover_extender_modes ──────────────────────────
    raw_modes: dict = raw.get(CONF_MODES_SECTION, {})
    modes_list: dict = {}
    for mode_name, mcfg in raw_modes.items():
        try:
            modes_list[mode_name] = _MODE_DISPLAY_SCHEMA(mcfg or {})
        except vol.Invalid as err:
            _LOGGER.warning("Cover config: invalid mode_display '%s': %s", mode_name, err)

    # ── Validate and normalise cover profiles ────────────────────────────────
    profiles: dict = {}
    for entity_id, cfg in raw.items():
        if not (isinstance(entity_id, str) and entity_id.startswith("cover.")):
            continue
        try:
            profiles[entity_id] = _COVER_PROFILE_SCHEMA(cfg or {})
        except vol.Invalid as err:
            _LOGGER.error("Cover config: invalid profile '%s': %s — skipped", entity_id, err)
            continue
        for mode_name in profiles[entity_id].get(CONF_MODES, {}):
            if mode_name not in modes_list:
                _LOGGER.warning(
                    "%s: mode '%s' not found in cover_extender_modes — lock/icon undefined",
                    entity_id, mode_name,
                )

    # ── Parse value_as_sensor ────────────────────────────────────────────────
    raw_vas: dict = raw.get(CONF_VALUE_AS_SENSOR, {})
    value_as_sensor = {
        "sun_facing":        bool(raw_vas.get("sun_facing",        False)),
        "enable_auto_shade": bool(raw_vas.get("enable_auto_shade", False)),
    }

    # ── Parse solar_gain global config ───────────────────────────────────────
    raw_solar_gain: dict = raw.get(CONF_SOLAR_GAIN, {})
    try:
        solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA(raw_solar_gain)
    except vol.Invalid as err:
        _LOGGER.warning("Cover config: invalid solar_gain config: %s", err)
        solar_gain_global = _SOLAR_GAIN_GLOBAL_SCHEMA({})

    _LOGGER.info("Loaded %d cover profiles from %s", len(profiles), source)
    return profiles, modes_list, facades, value_as_sensor, solar_gain_global


# ── Voluptuous schemas ────────────────────────────────────────────────────────

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_SOURCE): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_FACADE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AZIMUTH): vol.Coerce(float),
    }
)

_MODE_DISPLAY_SCHEMA = vol.Schema(
    {
        vol.Optional("icon",                 default="mdi:help-circle"): cv.string,
        vol.Optional("color",                default="white"):           cv.string,
        vol.Optional("lock",                 default=False):             cv.boolean,
        vol.Optional("auto_shade",           default=False):             cv.boolean,
        vol.Optional("solar_gain",           default=False):             cv.boolean,
        vol.Optional("hidden",               default=False):             cv.boolean,
    }
)

_SHADING_SCHEMA = vol.Schema(
    {
        vol.Optional("enable",            default=False): cv.boolean,
        vol.Optional("distance",          default=0.3):   vol.Coerce(float),
        vol.Optional("max_height",        default=1.5):   vol.Coerce(float),
        vol.Optional("min_height",        default=0.0):   vol.Coerce(float),
        vol.Optional("degrees",           default=90):    vol.Coerce(float),
        vol.Optional("max_elevation",     default=90):    vol.Coerce(float),
        vol.Optional("min_elevation",     default=5):     vol.Coerce(float),
        vol.Optional("minimum_position",  default=10):    vol.Coerce(float),
        vol.Optional("default_position",  default=100):   vol.Coerce(float),
        vol.Optional("change_threshold",  default=5):     vol.Coerce(float),
        vol.Optional("time_out",          default=1):     vol.Coerce(float),
    }
)

_SOLAR_GAIN_COVER_SCHEMA = vol.Schema(
    {
        vol.Optional("enable",          default=False): cv.boolean,
        vol.Optional("position_cold",   default=0):     vol.Coerce(int),
        vol.Optional("position_solar",  default=100):   vol.Coerce(int),
    }
)

_SOLAR_GAIN_GLOBAL_SCHEMA = vol.Schema(
    {
        vol.Optional("temperature_entity"):                       cv.entity_id,
        vol.Optional("temperature_threshold", default=19.0):     vol.Coerce(float),
        vol.Optional("weather_entity"):                          cv.entity_id,
        vol.Optional("good_conditions",       default=[]):       vol.All(cv.ensure_list, [cv.string]),
    }
)

_COVER_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FACADE):                         cv.string,
        vol.Optional(CONF_ENTITY_PICTURE):                 cv.string,
        vol.Optional(CONF_ANGLE_LEFT,        default=85.0):  vol.Coerce(float),
        vol.Optional(CONF_ANGLE_RIGHT,       default=85.0):  vol.Coerce(float),
        vol.Optional(CONF_MODES,             default={}):
            vol.Schema({cv.string: vol.Any(None, vol.Coerce(int), cv.entity_id)}),
        vol.Optional(CONF_SHADING,           default={}):    _SHADING_SCHEMA,
        vol.Optional(CONF_SOLAR_GAIN,       default={}):    _SOLAR_GAIN_COVER_SCHEMA,
        vol.Optional(CONF_EXCLUSION,         default=[]):    vol.All(
            cv.ensure_list, [cv.entity_id]
        ),
    }
)


# ── Coordinator ───────────────────────────────────────────────────────────────

class CoverExtenderCoordinator:
    """Encapsulates all business logic for cover_extender.

    Owns the command queue, persistent memory, event listeners, and service
    handlers. async_setup() only instantiates this class, registers services,
    and wires lifecycle hooks — keeping async_setup() to ~40 lines.
    """

    _COMMAND_INTERVAL = 0.15  # seconds between two physical cover commands

    def __init__(self, hass: HomeAssistant, source: str) -> None:
        self.hass = hass
        self._source = source
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cover_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        # Reverse maps rebuilt on every _setup_profiles call
        self._select_to_cover: dict[str, str] = {}
        self._lock_to_cover: dict[str, str] = {}
        self._entity_mode_map: dict[str, list[tuple[str, str]]] = {}
        # Listener unsubscribe callbacks (rebuilt on every _setup_profiles call)
        self._unsubs: list[Callable[[], None]] = []

    # ── Shortcuts to shared hass.data ────────────────────────────────────────

    @property
    def _profiles(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN].get(DATA_COVER_PROFILES, {})

    @property
    def _modes_list(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN].get(DATA_MODES, {})

    @property
    def _facades(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN].get(DATA_FACADES, {})

    # ── Queue ─────────────────────────────────────────────────────────────────

    def _start_worker(self) -> None:
        """(Re)start the queue worker, cancelling any previous instance."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self._worker_task = self.hass.async_create_background_task(
            self._cover_queue_worker(), "cover_extender_queue_worker"
        )

    async def _cover_queue_worker(self) -> None:
        """Send queued cover commands with a minimum 150 ms interval between each."""
        try:
            while True:
                service, data = await self._cover_queue.get()
                try:
                    await self.hass.services.async_call("cover", service, data)
                except Exception as err:
                    _LOGGER.warning(
                        "cover_extender: cover.%s %s failed: %s", service, data, err
                    )
                finally:
                    self._cover_queue.task_done()
                await asyncio.sleep(self._COMMAND_INTERVAL)
        except asyncio.CancelledError:
            pass

    def _enqueue_cover(self, service: str, data: dict) -> None:
        """Add a physical cover command to the global queue."""
        _LOGGER.debug("cover_extender: enqueue cover.%s %s", service, data)
        self._cover_queue.put_nowait((service, data))

    # ── Persistent memory ─────────────────────────────────────────────────────

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
        self.hass.async_create_task(self._store.async_save(dict(mem)))

    # ── Autonomous shade / solar gain ────────────────────────────────────────

    @callback
    def _apply_shade(self, entity_id: str, cfg: dict[str, Any]) -> None:
        """Apply shade position automatically when switch.<cover>_auto_shade is ON.

        Only acts when should_update=True (respects change_threshold and time_out).
        """
        cover_name = entity_id.split(".")[1]
        auto_sw = self.hass.states.get(f"switch.{cover_name}_auto_shade")
        if not auto_sw or auto_sw.state != "on":
            _LOGGER.debug("auto_shade %s: switch missing or off → skipped", entity_id)
            return
        position, should_update = _compute_shade_sync(self.hass, entity_id, cfg)
        if not should_update:
            return
        _LOGGER.debug("auto_shade %s → %d%%", entity_id, position)
        self._enqueue_cover("set_cover_position", {"entity_id": entity_id, "position": position})

    @callback
    def _apply_solar_gain(self, entity_id: str, cfg: dict[str, Any]) -> None:
        """Apply solar gain position based on temperature, sun facing, and weather.

        - switch.<cover>_auto_solar_gain off → skipped
        - temp >= threshold             → no action (stay at current position)
        - temp < threshold AND sun_facing AND weather_ok → position_solar (Y)
        - temp < threshold AND (not sun_facing OR not weather_ok) → position_cold (X)
        """
        cover_name = entity_id.split(".")[1]
        solar_gain_sw = self.hass.states.get(f"switch.{cover_name}_auto_solar_gain")
        if not solar_gain_sw or solar_gain_sw.state != "on":
            _LOGGER.debug("auto_solar_gain %s: switch missing or off → skipped", entity_id)
            return

        solar_gain_cfg = cfg.get(CONF_SOLAR_GAIN, {})
        global_solar_gain = self.hass.data[DOMAIN].get(DATA_SOLAR_GAIN, {})

        # ── Temperature check ────────────────────────────────────────────────
        temp_entity = global_solar_gain.get("temperature_entity")
        threshold = float(global_solar_gain.get("temperature_threshold", 19.0))
        if temp_entity:
            temp_state = self.hass.states.get(temp_entity)
            if not temp_state:
                _LOGGER.warning("auto_solar_gain %s: temperature entity '%s' not found", entity_id, temp_entity)
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

        # ── Sun + weather check ──────────────────────────────────────────────
        sun_facing = _compute_sun_facing(self.hass, cfg, self._facades)

        weather_ok = True  # no weather restriction if not configured
        weather_entity = global_solar_gain.get("weather_entity")
        good_conditions: list[str] = global_solar_gain.get("good_conditions", [])
        if weather_entity and good_conditions:
            weather_st = self.hass.states.get(weather_entity)
            if weather_st:
                weather_ok = weather_st.state in good_conditions
            else:
                _LOGGER.warning("auto_solar_gain %s: weather entity '%s' not found", entity_id, weather_entity)
                weather_ok = False

        if sun_facing and weather_ok:
            position = int(solar_gain_cfg.get("position_solar", 100))
        else:
            position = int(solar_gain_cfg.get("position_cold", 0))

        _LOGGER.debug(
            "auto_solar_gain %s: sun_facing=%s, weather_ok=%s → %d%%",
            entity_id, sun_facing, weather_ok, position,
        )
        self._enqueue_cover("set_cover_position", {"entity_id": entity_id, "position": position})

    # ── Mode application ──────────────────────────────────────────────────────

    async def _apply_mode_core(
        self,
        entity_id: str,
        mode: str,
        from_mode: str | None,
    ) -> None:
        """Apply a mode to a cover — internal logic.

        Called by the select listener (from_mode always correct) or by the
        apply_mode service (via select.select_option → listener).
        Does NOT update the select entity: it is already up-to-date at call time.
        """
        cfg = self._profiles.get(entity_id)
        if not cfg or mode not in cfg.get(CONF_MODES, {}):
            _LOGGER.debug("_apply_mode_core: mode '%s' not configured for %s", mode, entity_id)
            return

        cover_name    = entity_id.split(".")[1]
        lock_id       = f"switch.{cover_name}_lock"
        shading_id    = f"switch.{cover_name}_auto_shade"

        from_mode_cfg = self._modes_list.get(from_mode, {}) if from_mode else {}
        to_mode_cfg   = self._modes_list.get(mode, {})

        cover_state  = self.hass.states.get(entity_id)
        current_pos  = cover_state.attributes.get("current_position") if cover_state else None
        old_memory   = self._get_memory(entity_id)

        # 1. save_on_enter (always)
        if current_pos is not None:
            await self._set_memory(entity_id, int(current_pos))

        # 2. Lock
        mode_lock = bool(to_mode_cfg.get("lock", False))
        await self.hass.services.async_call(
            "switch", "turn_on" if mode_lock else "turn_off",
            {"entity_id": lock_id},
        )

        # 3. auto_shade
        if to_mode_cfg.get("auto_shade", False):
            await self.hass.services.async_call("switch", "turn_on", {"entity_id": shading_id})
            await self.hass.services.async_call("switch", "turn_on", {"entity_id": lock_id})
        else:
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": shading_id})

        # 3b. auto_solar_gain
        solar_gain_id = f"switch.{cover_name}_auto_solar_gain"
        if to_mode_cfg.get("solar_gain", False):
            await self.hass.services.async_call("switch", "turn_on", {"entity_id": solar_gain_id})
            await self.hass.services.async_call("switch", "turn_on", {"entity_id": lock_id})
        else:
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": solar_gain_id})

        # 4. Position (skipped if solar_gain — _apply_solar_gain determines position)
        if not to_mode_cfg.get("solar_gain", False):
            fixed_position = cfg.get(CONF_MODES, {}).get(mode)
            if fixed_position is not None:
                target_position = _resolve_mode_position(self.hass, fixed_position)
                consume_memory  = False
            elif not from_mode_cfg.get("lock", False) and old_memory is not None:
                target_position = old_memory
                consume_memory  = True
            else:
                if from_mode_cfg.get("lock", False):
                    _LOGGER.debug(
                        "_apply_mode_core '%s' → %s: previous mode was locked, memory not restored",
                        mode, entity_id,
                    )
                else:
                    _LOGGER.debug(
                        "_apply_mode_core '%s' → %s: no fixed position and no stored memory → no move",
                        mode, entity_id,
                    )
                target_position = None
                consume_memory  = False

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
                        "set_cover_position", {"entity_id": entity_id, "position": target_position}
                    )
                    if consume_memory:
                        await self._set_memory(entity_id, None)

        # 5. Solar gain: initial position on mode entry
        if to_mode_cfg.get("solar_gain", False):
            self._apply_solar_gain(entity_id, cfg)

        _LOGGER.debug(
            "_apply_mode_core '%s' → %s (from=%s, lock=%s, position=%s)",
            mode, entity_id, from_mode, mode_lock, target_position,
        )

    # ── Listeners ─────────────────────────────────────────────────────────────

    @callback
    def _setup_profiles(self) -> None:
        """Register profiles and (re)create all event listeners.

        Called at startup and on every reload. Cancels previous listeners before
        creating new ones. Reads profiles from self._profiles
        (hass.data[DOMAIN][DATA_COVER_PROFILES]) — the caller must write them there first.
        """
        profiles = self._profiles

        # Cancel previous listeners
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

        # Reverse maps used by select/lock listeners
        self._select_to_cover = {
            f"select.mode_{eid.split('.')[1]}": eid for eid in profiles
        }
        self._lock_to_cover = {
            f"switch.{eid.split('.')[1]}_lock": eid for eid in profiles
        }

        # Position-entity → [(cover_id, mode_name)] map
        self._entity_mode_map = {}
        for cover_id, cfg in profiles.items():
            for mode_name, raw_pos in cfg.get(CONF_MODES, {}).items():
                if isinstance(raw_pos, str):
                    self._entity_mode_map.setdefault(raw_pos, []).append((cover_id, mode_name))

        # Register listeners
        self._unsubs = [
            async_track_state_change_event(
                self.hass, list(profiles.keys()), self._handle_cover_state_change
            ),
            async_track_state_change_event(
                self.hass, ["sun.sun"], self._inject_sun_facing
            ),
            async_track_state_change_event(
                self.hass, list(self._select_to_cover.keys()), self._handle_select_mode_change
            ),
            async_track_state_change_event(
                self.hass, list(self._lock_to_cover.keys()), self._handle_lock_off
            ),
        ]
        if self._entity_mode_map:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, list(self._entity_mode_map.keys()), self._handle_mode_entity_change
                )
            )

        # Solar gain: listen to temperature and weather entity changes
        global_solar_gain = self.hass.data[DOMAIN].get(DATA_SOLAR_GAIN, {})
        solar_gain_watch: list[str] = []
        if temp_ent := global_solar_gain.get("temperature_entity"):
            solar_gain_watch.append(temp_ent)
        if weather_ent := global_solar_gain.get("weather_entity"):
            solar_gain_watch.append(weather_ent)
        if solar_gain_watch:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, solar_gain_watch, self._handle_solar_gain_trigger
                )
            )

        # Initial attribute injection on already-loaded covers
        for entity_id, cfg in profiles.items():
            extra_attrs = _build_extra_attrs(cfg, memory=self._get_memory(entity_id))
            if not extra_attrs:
                continue
            state = self.hass.states.get(entity_id)
            if state:
                current_attrs = dict(state.attributes)
                if not all(current_attrs.get(k) == v for k, v in extra_attrs.items()):
                    self.hass.states.async_set(entity_id, state.state, {**current_attrs, **extra_attrs})

        self._inject_sun_facing()

    @callback
    def _handle_cover_state_change(self, event: Event) -> None:
        """Re-inject custom attributes on every cover state change."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        profiles = self._profiles
        if not new_state or entity_id not in profiles:
            return
        extra_attrs = _build_extra_attrs(profiles[entity_id], memory=self._get_memory(entity_id))
        if not extra_attrs:
            return
        current_attrs = dict(new_state.attributes)
        # Guard against infinite loops: only update if attributes actually differ
        if all(current_attrs.get(k) == v for k, v in extra_attrs.items()):
            return
        self.hass.states.async_set(entity_id, new_state.state, {**current_attrs, **extra_attrs})

    @callback
    def _inject_sun_facing(self, _event: Event | None = None) -> None:
        """Recompute and inject sun_facing on all covers on each sun.sun state change."""
        profiles = self._profiles
        facades = self._facades
        modes_list = self._modes_list
        for entity_id, cfg in profiles.items():
            sun_facing = _compute_sun_facing(self.hass, cfg, facades)
            if sun_facing is not None:
                state = self.hass.states.get(entity_id)
                if state:
                    current_attrs = dict(state.attributes)
                    if current_attrs.get(ATTR_SOLEIL_EN_FACE) != sun_facing:
                        self.hass.states.async_set(
                            entity_id, state.state,
                            {**current_attrs, ATTR_SOLEIL_EN_FACE: sun_facing},
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
        """Apply the stored memory position when the lock is released.

        Blocked if any entity defined in the profile's `exclusion:` list is ON.
        """
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not old_state:
            return
        if old_state.state != "on" or new_state.state != "off":
            return
        cover_id = self._lock_to_cover.get(event.data.get("entity_id"))
        if not cover_id:
            return
        cfg = self._profiles.get(cover_id, {})
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
        new_state = event.data.get("new_state")
        if not new_state:
            return
        try:
            new_position = int(float(new_state.state))
        except (ValueError, TypeError):
            return
        for cover_id, mode_name in self._entity_mode_map.get(ref_entity, []):
            cover_name = cover_id.split(".")[1]
            select_state = self.hass.states.get(f"select.mode_{cover_name}")
            if not select_state or select_state.state != mode_name:
                continue
            _LOGGER.debug(
                "mode entity '%s' → %d%% : application sur %s (mode=%s)",
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

    # ── Service handlers ──────────────────────────────────────────────────────

    async def service_apply_mode(self, call: ServiceCall) -> dict:
        """Apply a mode to one or more covers via select.select_option.

        Thin wrapper: updates the select, which fires the internal listener
        _handle_select_mode_change → _apply_mode_core (lock, memory, position).
        Returns {"applied": [...], "skipped": [...]} usable as a response variable.
        """
        mode: str = call.data["mode"]
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
            select_id = f"select.mode_{cover_name}"
            if not self.hass.states.get(select_id):
                _LOGGER.warning(
                    "apply_mode: entity '%s' not found — component not ready yet?",
                    select_id,
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
        mode: str = call.data["mode"]
        cfg = self._profiles.get(entity_id)
        if not cfg or mode not in cfg.get(CONF_MODES, {}):
            return {"position": None}
        return {"position": cfg[CONF_MODES][mode]}

    async def service_compute_shade_position(self, call: ServiceCall) -> dict:
        """Compute the solar shade position for a cover and return it with a should_update flag."""
        entity_id: str = call.data["entity_id"]
        cfg = self._profiles.get(entity_id, {})
        position, should_update = _compute_shade_sync(self.hass, entity_id, cfg)
        _LOGGER.debug(
            "compute_shade_position %s → %d%% (update=%s)", entity_id, position, should_update
        )
        return {"position": position, "should_update": should_update}

    async def _set_cover_position_impl(self, entity_ids: list[str], position: int) -> None:
        """Shared logic: move or store in memory depending on lock state."""
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
        """Move one or more covers, respecting the lock (switch.<cover>_lock)."""
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
            self._enqueue_cover("set_cover_position", {"entity_id": entity_id, "position": position})

    async def service_reload(self, call: ServiceCall) -> None:
        """Reload cover configuration from YAML without restarting HA."""
        new_profiles, new_modes_list, new_facades, new_vas, new_solar_gain = await self.hass.async_add_executor_job(
            _load_covers_config, self.hass, self._source
        )
        self.hass.data[DOMAIN][DATA_COVER_PROFILES] = new_profiles
        self.hass.data[DOMAIN][DATA_MODES] = new_modes_list
        self.hass.data[DOMAIN][DATA_FACADES] = new_facades
        self.hass.data[DOMAIN][DATA_VALUE_AS_SENSOR] = new_vas
        self.hass.data[DOMAIN][DATA_SOLAR_GAIN] = new_solar_gain
        self._setup_profiles()
        async_dispatcher_send(self.hass, SIGNAL_COVER_RELOAD)
        _LOGGER.info("cover_extender reloaded (%d profiles)", len(new_profiles))

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Load config, start the worker, and register the homeassistant_started listener.

        Platform loading is handled by async_setup_entry via async_forward_entry_setups.
        _setup_profiles() is deferred to homeassistant_started so that cover entities
        managed by other integrations are already in the state machine.
        """
        stored = await self._store.async_load() or {}
        self.hass.data[DOMAIN][DATA_MEMORY] = {k: int(v) for k, v in stored.items()}

        self._start_worker()

        profiles, modes_list, facades, value_as_sensor, solar_gain_global = await self.hass.async_add_executor_job(
            _load_covers_config, self.hass, self._source
        )
        self.hass.data[DOMAIN][DATA_COVER_PROFILES] = profiles
        self.hass.data[DOMAIN][DATA_MODES] = modes_list
        self.hass.data[DOMAIN][DATA_FACADES] = facades
        self.hass.data[DOMAIN][DATA_VALUE_AS_SENSOR] = value_as_sensor
        self.hass.data[DOMAIN][DATA_SOLAR_GAIN] = solar_gain_global

        # _setup_profiles requires cover entities to already be in the state machine
        self.hass.bus.async_listen_once("homeassistant_started", lambda _: self._setup_profiles())

    async def async_stop(self, _event: Event | None = None) -> None:
        """Cancel the worker and unsubscribe all listeners."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


# ── Entry points ──────────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Import existing YAML configuration as a config entry (backward compat)."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cover_extender from a config entry."""
    source = entry.data.get(CONF_SOURCE)
    if not source:
        _LOGGER.error("'%s' is required in cover_extender configuration", CONF_SOURCE)
        return False

    hass.data.setdefault(DOMAIN, {})

    coordinator = CoverExtenderCoordinator(hass, source)
    hass.data[DOMAIN]["coordinator"] = coordinator

    await coordinator.async_start()

    # Forward to platform setup — platforms read DATA_COVER_PROFILES from hass.data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _cover_only_schema = vol.Schema({vol.Required("entity_id"): cv.entity_ids})

    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_MODE, coordinator.service_apply_mode,
        schema=vol.Schema({
            vol.Required("mode"): cv.string,
            vol.Required("entity_id"): cv.entity_ids,
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD, coordinator.service_reload,
        schema=vol.Schema({}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_MODE_POSITION, coordinator.service_get_mode_position,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("mode"): cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPUTE_SHADE_POSITION, coordinator.service_compute_shade_position,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_id}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_COVER_POSITION, coordinator.service_set_cover_position,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_ids,
            vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_OPEN_COVER, coordinator.service_open_cover, schema=_cover_only_schema
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLOSE_COVER, coordinator.service_close_cover, schema=_cover_only_schema
    )
    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_MEMORY, coordinator.service_apply_memory,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_ids}),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a cover_extender config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: CoverExtenderCoordinator | None = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_stop()
        hass.data[DOMAIN].pop("coordinator", None)
        for service in (
            SERVICE_APPLY_MODE, SERVICE_RELOAD, SERVICE_GET_MODE_POSITION,
            SERVICE_COMPUTE_SHADE_POSITION, SERVICE_SET_COVER_POSITION,
            SERVICE_OPEN_COVER, SERVICE_CLOSE_COVER, SERVICE_APPLY_MEMORY,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok
