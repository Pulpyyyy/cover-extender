# Cover Extender

A Home Assistant custom component that enriches existing cover (blind/shutter) entities with advanced automation features: mode management, position memory, automation lock, and autonomous solar shading — without modifying or replacing your original cover entities.

## Features

- **Mode system** — define named positions (Night, Day, Heat-wave…) with icons, colors, and behaviors
- **Automation lock** — block automated moves while preserving the intended position in memory
- **Position memory** — stores a target position that is applied on lock release
- **Autonomous solar shading** — automatically tracks the sun and adjusts cover position (no blueprint required)
- **Non-destructive** — injects attributes into existing cover entities, never replaces them
- **Hot reload** — reload the YAML config without restarting Home Assistant

## Installation

1. Copy the `cover_extender` folder into `custom_components/`
2. Add the following to `configuration.yaml`:

```yaml
cover_extender:
  source: yaml_entities/covers_config.yaml
```

3. Restart Home Assistant

## Configuration

All cover profiles live in a single YAML file referenced by `source:`.

### Minimal example

```yaml
# covers_config.yaml

facades:
  south:
    azimuth: 180.0
  east:
    azimuth: 90.0

cover_extender_modes:
  Night:
    icon: mdi:moon-waning-crescent
    color: indigo
  Day:
    icon: mdi:white-balance-sunny
    color: orange
  Shade:
    icon: mdi:sun-clock
    color: amber
    lock: true
    auto_shade: true
  Heat-wave:
    icon: mdi:thermometer-alert
    color: "#FF6600"

cover.living_room_blind:
  facade: south
  modes:
    Night: 100
    Day: 40
    Shade: null                             # position computed from sun geometry
    Heat-wave: input_number.heatwave_pos   # position tracked from an entity
  angle_left: 80.0
  angle_right: 80.0
  enable_auto_shade: true
  shading:
    distance: 0.4
    max_height: 1.8
    minimum_position: 15
    change_threshold: 5
    time_out: 2
  exclusion:
    - input_boolean.vacation_mode

cover.bedroom_blind:
  facade: east
  modes:
    Night: 100
    Day: 0
```

### `facades` block

| Key | Type | Description |
|-----|------|-------------|
| `azimuth` | float | Compass direction the facade faces (0 = North, 90 = East, 180 = South, 270 = West) |

### `cover_extender_modes` block

| Key | Default | Description |
|-----|---------|-------------|
| `icon` | `mdi:help-circle` | Material Design Icon for the mode |
| `color` | `white` | **6-digit hex only** (`#RRGGBB`) — 8-digit hex (`#RRGGBBaa`) is not supported and will be ignored by UI cards |
| `lock` | `false` | Activate the automation lock when entering this mode |
| `auto_shade` | `false` | Activate autonomous solar shading when entering this mode |
| `helio` | `false` | Mark this mode as heliotropic (used by UI cards to apply dynamic sun-tracking logic) |
| `hidden` | `false` | Hide this mode from UI cards |

### Per-cover profile

| Key | Default | Description |
|-----|---------|-------------|
| `facade` | — | Facade name (must match a key in `facades`) |
| `modes` | `{}` | Dict of `mode_name: position` — value can be an integer 0–100, `null` (no fixed position, e.g. solar shading), or an entity ID whose numeric state is used as the position (tracked live) |
| `angle_left` | `85.0` | Sun cone tolerance left of facade azimuth (degrees) |
| `angle_right` | `85.0` | Sun cone tolerance right of facade azimuth (degrees) |
| `enable_auto_shade` | `false` | Create the `auto_shade` switch for this cover |
| `entity_picture` | — | URL of a custom image shown on the cover tile |
| `ombrage` | `{}` | Solar shading parameters (see below) |
| `exclusion` | `[]` | List of entity IDs — moves are blocked while any of these is `on` |

### `ombrage` sub-block (solar shading)

| Key | Default | Description |
|-----|---------|-------------|
| `distance` | `0.3` | Obstacle depth in metres (balcony overhang, awning…) |
| `max_height` | `1.5` | Shutter max height in metres |
| `min_height` | `0.0` | Shutter min height in metres |
| `degrees` | `90` | Solar cone half-angle — how far left/right of facade the sun must be |
| `max_elevation` | `90` | Upper sun elevation bound (degrees) |
| `min_elevation` | `5` | Lower sun elevation bound — ignores sunrise/sunset glare |
| `minimum_position` | `10` | Floor position (%) when sun is in the cone |
| `default_position` | `100` | Position (%) when sun is outside the cone |
| `change_threshold` | `5` | Min difference (%) to trigger a move — prevents jitter |
| `time_out` | `1` | Minimum delay between two automated moves (minutes) |

## Entities created per cover

For each configured cover entity the component automatically creates:

| Entity | Purpose |
|--------|---------|
| `select.mode_<cover>` | Mode selector — change mode via UI or automations |
| `number.<cover>_memory` | Stored target position (diagnostic, not shown in main dashboard) |
| `switch.<cover>_lock` | Automation lock — ON blocks physical moves, stores them in memory instead |
| `switch.<cover>_auto_shade` | Autonomous solar shading toggle *(only if `enable_auto_shade: true`)* |

Attributes injected into the cover entity:
- `facade`, `modes`, `enable_auto_shade`, `sun_facing`, `entity_picture`

Attributes exposed by `select.mode_<cover>` (and `select.cover_extender_modes`):

| Attribute | Description |
|-----------|-------------|
| `options` | List of mode names available for this cover |
| `icon` | MDI icon of the **currently selected** mode |
| `color` | Hex color of the **currently selected** mode |
| `modes_list` | Dict of **all** modes → `{icon, color, lock, save_on_enter, apply_memory_on_exit, auto_shade, helio}` — used by UI cards to render chips without hardcoding colors |

## Services

### `cover_extender.set_cover_position`
Moves covers to a position, respecting the lock (writes to memory if locked).

```yaml
service: cover_extender.set_cover_position
data:
  entity_id: cover.living_room_blind
  position: 50
```

### `cover_extender.open_cover` / `cover_extender.close_cover`
Lock-aware open (100%) and close (0%).

### `cover_extender.apply_mode`
Apply a named mode to one or more covers. Returns `{applied: [...], skipped: [...]}`.

```yaml
service: cover_extender.apply_mode
data:
  entity_id:
    - cover.living_room_blind
    - cover.bedroom_blind
  mode: Night
```

### `cover_extender.apply_memory`
Force a cover to its stored memory position, ignoring lock state.

### `cover_extender.compute_shade_position`
Returns `{position: int, should_update: bool}` for the current sun position.

### `cover_extender.get_mode_position`
Returns `{position: int|null}` for a given mode on a cover.

### `cover_extender.reload`
Reloads the YAML config file without restarting Home Assistant.

## Lock / Memory pattern

The lock system solves a common automation conflict: a scheduled automation wants to move a cover, but the user has manually positioned it and doesn't want it disturbed.

1. **Lock ON** → any `set_cover_position` call writes to memory instead of moving the cover
2. **Lock OFF** → the stored memory position is applied automatically
3. Modes with `lock: true` activate the lock on entry; modes without it deactivate it

The `exclusion` list provides an additional guard: if any listed entity is `on` (e.g., `input_boolean.vacation_mode`), physical moves are blocked and stored in memory until the exclusion clears and the lock is released.

## Solar shading algorithm

When `switch.<cover>_auto_shade` is ON, the component listens to every `sun.sun` state change and computes a shutter position using:

```
h = (distance / cos(γ)) × tan(α)
```

Where `α` is the sun elevation and `γ` is the angular deviation between the sun azimuth and the facade azimuth. The resulting height is converted to a percentage, clamped to `[minimum_position, 100]`, and applied only if the difference exceeds `change_threshold` and the `time_out` delay has elapsed.
