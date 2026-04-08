"""Constants for cover_extender."""

DOMAIN = "cover_extender"

# Configuration keys
CONF_SOURCE = "source"
CONF_FACADE = "facade"
CONF_MODES = "modes"
CONF_ENTITY_PICTURE = "entity_picture"
CONF_ANGLE_LEFT = "angle_left"
CONF_ANGLE_RIGHT = "angle_right"
CONF_FACADES = "facades"
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

# Configuration key for show_entities section
CONF_SHOW_ENTITIES = "show_entities"

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

# Config key for global mode display definitions
CONF_MODES_SECTION = "cover_extender_modes"

# Dispatcher signal fired after a reload so select entities can refresh their options
SIGNAL_COVER_RELOAD = f"{DOMAIN}_reload"

# HA bus events
EVENT_MODE_CHANGED  = f"{DOMAIN}_mode_changed"
EVENT_MEMORY_SAVED  = f"{DOMAIN}_memory_saved"
EVENT_SHADE_APPLIED = f"{DOMAIN}_shade_applied"

# Configurable command interval (seconds between consecutive cover commands)
CONF_COMMAND_INTERVAL    = "command_interval"
DEFAULT_COMMAND_INTERVAL = 0.15

# Platform entity id suffixes  (domain.<suffix>)
ENTITY_ID_SELECT = "mode_{cover}"   # select.mode_volet_sam
ENTITY_ID_SWITCH = "{cover}_lock"   # switch.volet_sam_lock
