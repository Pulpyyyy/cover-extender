"""Constants for cover_extender."""

DOMAIN = "cover_extender"

# Configuration keys
CONF_FACADE = "facade"
CONF_MODES = "modes"
CONF_ENTITY_PICTURE = "entity_picture"
CONF_ANGLE_LEFT = "angle_left"
CONF_ANGLE_RIGHT = "angle_right"
CONF_AZIMUTH = "azimuth"

# State attributes injected into cover entities
ATTR_FACADE = "facade"
ATTR_MODES = "modes"
ATTR_ENABLE_AUTO_SHADE = "auto_shade"
ATTR_SUN_FACING = "sun_facing"

# Shading sub-config key and its fields (all optional, defaults in service)
CONF_SHADING      = "shade"
CONF_EXCLUSION    = "exclusion"

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

# Configurable command interval
# UI stores the value in milliseconds (int); the coordinator uses seconds (float).
CONF_COMMAND_INTERVAL       = "command_interval"
DEFAULT_COMMAND_INTERVAL_MS = 150    # stored in config data (ms, int)
DEFAULT_COMMAND_INTERVAL    = 0.15   # used internally by coordinator (seconds, float)

# Platform entity id suffixes  (domain.<suffix>)
ENTITY_ID_SELECT = "mode_{cover}"   # select.mode_volet_sam
ENTITY_ID_SWITCH = "{cover}_lock"   # switch.volet_sam_lock

# Config subentry types (UI mode)
SUBENTRY_TYPE_GLOBAL    = "global"
SUBENTRY_TYPE_FACADE    = "facade"
SUBENTRY_TYPE_MODE      = "mode"
SUBENTRY_TYPE_COVER     = "cover"
SUBENTRY_TYPE_TEMPLATE  = "cover_template"
