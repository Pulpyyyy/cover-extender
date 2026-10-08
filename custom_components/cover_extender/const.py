"""Constants for cover_extender."""

DOMAIN = "cover_extender"

# Configuration keys
CONF_FACADE = "facade"
CONF_MODES = "modes"
CONF_ENTITY_PICTURE = "entity_picture"
CONF_ANGLE_LEFT = "angle_left"
CONF_ANGLE_RIGHT = "angle_right"
CONF_AZIMUTH = "azimuth"
# A facade's slope: the glass's angle with the horizontal. 90 is a wall (the
# default, and every facade stored before it existed), 30 a roof window in a
# 30° roof, 0 a flat skylight. Below FLAT_TILT the window counts as flat.
CONF_TILT = "tilt"
WALL_TILT = 90
FLAT_TILT = 10
# The kind of window a template is for: its heights are a wall's, its lengths a
# roof's. Only "roof" and "flat" are stored; a template without it is a wall's.
CONF_WINDOW_KIND = "kind"
WINDOW_KINDS = ("wall", "roof", "flat")

# State attributes injected into cover entities
ATTR_FACADE = "facade"
ATTR_MODES = "modes"
ATTR_ENABLE_AUTO_SHADE = "auto_shade"
ATTR_SUN_FACING = "sun_facing"

# Shading sub-config key and its fields (all optional, defaults in service)
CONF_SHADING      = "shade"
CONF_EXCLUSION    = "exclusion"   # safety: blocks every move, priority included
CONF_INHIBITION   = "inhibition"  # blocks every move except priority requests
CONF_SCHEDULE     = "schedule"    # per cover: {"morning": mode|None, "evening": mode|None}

# Solar gain sub-config keys
CONF_SOLAR_GAIN  = "solar_gain"
DATA_SOLAR_GAIN  = "solar_gain_config"

# Service names
SERVICE_APPLY_MODE = "apply_mode"
SERVICE_RELOAD = "reload"
SERVICE_GET_MODE_POSITION = "get_mode_position"
SERVICE_COMPUTE_SHADE_POSITION = "compute_shade_position"
SERVICE_SET_COVER_POSITION = "set_cover_position"
SERVICE_OPEN_COVER         = "open_cover"
SERVICE_CLOSE_COVER        = "close_cover"
SERVICE_APPLY_MEMORY       = "apply_memory"
SERVICE_END_TIMED_MODE     = "end_timed_mode"

# hass.data keys
DATA_COVER_PROFILES      = "cover_profiles"
DATA_MODES               = "cover_extender_modes"
DATA_FACADES             = "facades"
DATA_SHOW_ENTITIES       = "show_entities_config"
DATA_SELECT_COVER_IDS      = "select_cover_ids"
DATA_SWITCH_COVER_IDS      = "switch_cover_ids"
DATA_SWITCH_AUTO_SHADE_IDS = "auto_shade_cover_ids"
DATA_SWITCH_AUTO_SOLAR_GAIN_IDS = "auto_solar_gain_cover_ids"
DATA_BINARY_SENSOR_SUN_FACING_IDS        = "binary_sensor_sun_facing_ids"
DATA_BINARY_SENSOR_AUTO_SHADE_IDS        = "binary_sensor_auto_shade_ids"
DATA_BINARY_SENSOR_AUTO_SOLAR_GAIN_IDS   = "binary_sensor_solar_gain_ids"
DATA_MEMORY                = "memory"

STORAGE_KEY     = f"{DOMAIN}.memory"
# Running countdowns of timed modes, so they survive a restart.
TIMERS_STORAGE_KEY = f"{DOMAIN}.timers"
# Last day each schedule ran, to catch a missed one up after a restart.
SCHEDULE_STORAGE_KEY = f"{DOMAIN}.schedule"
STORAGE_VERSION = 1

# Dispatcher signal fired after a reload so select entities can refresh their options
SIGNAL_COVER_RELOAD = f"{DOMAIN}_reload"

# ── External attributes contract (shared, cross-integration) ──────────────────
# Neutral namespace owned by neither integration. It lets a target cover entity
# (e.g. ESPSomfy-RTS) carry the extras we would otherwise force onto it with a
# hass.states.async_set on every state change — the source of an attribute
# ping-pong and entity_picture flicker. When the target declares itself a
# "reader" we deposit the extras here and fire EXTERNAL_ATTRS_SIGNAL instead of
# writing its state; the entity then merges them through its own property.
# Covers that are NOT readers (velux mqtt, esphome, older firmware) keep the
# direct async_set fallback unchanged.
EXTERNAL_ATTRS_DATA   = "cover_external_attrs"
EXTERNAL_ATTRS_SIGNAL = "cover_external_attrs_updated"

# HA bus events
EVENT_MODE_CHANGED  = f"{DOMAIN}_mode_changed"
EVENT_MEMORY_SAVED  = f"{DOMAIN}_memory_saved"
EVENT_SHADE_APPLIED = f"{DOMAIN}_shade_applied"
EVENT_TIMED_MODE_ENDED = f"{DOMAIN}_timed_mode_ended"

# Timed modes: bounds of a mode duration, in minutes (24 h at most), the
# attributes the cover's mode selector exposes, and the dispatcher signal
# that tells it to redraw them.
MODE_DURATION_MIN = 1
MODE_DURATION_MAX = 1440
ATTR_MODE_ENDS_AT = "mode_ends_at"
ATTR_RETURN_MODE  = "return_mode"
SIGNAL_TIMED_MODE = f"{DOMAIN}_timed_mode"
# The day's opening / closing times changed (new day, event, settings).
SIGNAL_SCHEDULE   = f"{DOMAIN}_schedule"
# binary_sensor.cx_day, found by this id once it may have been renamed.
DAY_UNIQUE_ID     = f"{DOMAIN}_binary_sensor_cx_day"

# Weather states accepted as "good conditions" for solar gain. Shared so the
# config flow and the admin panel offer the same list (the panel receives it
# through config/get rather than hard-coding a second copy in JavaScript).
WEATHER_CONDITIONS = [
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
]

# The integration's own device (service type): hosts the global helpers, the
# helpers of covers that have no device, and the link to the admin panel.
HUB_IDENTIFIER = "hub"

# Repairs: the 4.0 rename of the helper entity ids (see __init__._migrate_entity_ids_v4).
ISSUE_ENTITY_IDS_RENAMED = "entity_ids_renamed"

# Configurable command interval
# UI stores the value in milliseconds (int); the coordinator uses seconds (float).
CONF_COMMAND_INTERVAL       = "command_interval"
DEFAULT_COMMAND_INTERVAL_MS = 150    # stored in config data (ms, int)
DEFAULT_COMMAND_INTERVAL    = 0.15   # used internally by coordinator (seconds, float)

# (The conventional helper entity ids live in helpers._HELPER_CONVENTIONAL_EIDS,
# next to the unique_id templates they must stay consistent with.)

# ── Admin frontend (admin panel) ──────────────────────────────────────────────
# The admin UI is a JS panel served by the integration itself (no www/ file,
# no Lovelace resource). Also reachable through the hub device's
# configuration_url and the /cover-extender URL directly.
URL_BASE         = "/cover_extender_frontend"
ADMIN_JS         = "cover-extender-admin.js"
PANEL_URL_PATH   = "cover-extender"          # → http://ha:8123/cover-extender
PANEL_NAME       = "cover-extender-panel"    # custom element defined by ADMIN_JS
FALLBACK_VERSION = "0.0.0"
# Sidebar entry: declaring a title is what lets each user show or hide it from
# HA's own sidebar editor. Not translated — async_register_built_in_panel takes
# a literal title, and the panel serves a single admin.
PANEL_SIDEBAR_TITLE = "Cover Extender"
PANEL_SIDEBAR_ICON  = "mdi:window-shutter-cog"

# WebSocket API commands (admin panel ↔ entry options)
WS_CONFIG_GET  = f"{DOMAIN}/config/get"
WS_CONFIG_SAVE = f"{DOMAIN}/config/save"
WS_SCHEDULE_PREVIEW = f"{DOMAIN}/schedule/preview"

# ── Configuration storage ─────────────────────────────────────────────────────
# Everything the panel edits lives under entry.options[OPT_CONFIG], one key per
# section:
#     {"global": {...flat settings...},
#      "facade": [...], "mode": [...], "cover": [...], "cover_template": [...]}
# Until v2.7 each section was a singleton config SUBENTRY. That worked, but the
# integration page renders one group per subentry type, so the five sections
# showed up there as five empty boxes — no device, no entity, nothing to click.
# The keys below keep the old subentry-type strings, so the v1 → v2 migration in
# __init__.py is a straight lift of subentry.data into this dict.
# The one section that is nested rather than flat is OPT_CONFIG itself: it keeps
# the container distinguishable from the pre-2.0 layout, which stored the global
# settings as bare flat keys directly in entry.options.
OPT_CONFIG      = "config"

SECTION_GLOBAL   = "global"
SECTION_FACADE   = "facade"
SECTION_MODE     = "mode"
SECTION_COVER    = "cover"
SECTION_TEMPLATE = "cover_template"
# The house's morning and evening schedules: {"morning": {...}, "evening": {...}}.
SECTION_SCHEDULE = "schedule"

# Sections holding a list of named items (global is a flat dict instead).
SECTIONS_WITH_ITEMS = (SECTION_FACADE, SECTION_MODE, SECTION_COVER, SECTION_TEMPLATE)

# The one config subentry type left, and it is not a subentry at all: the only
# flow registered under it aborts on its first step, so nothing is ever stored.
# Declaring a type is simply what puts the "Open the editor" button on the
# integration page.
SUBENTRY_TYPE_EDITOR = "editor"
