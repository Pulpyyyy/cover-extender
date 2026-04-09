# Cover Extender

Cover Extender is a Home Assistant custom integration that enriches existing cover (blind/shutter) entities with advanced automation features: mode management, automation lock, persistent memory, autonomous solar shading, and solar gain optimization — all without replacing or duplicating your cover entities.

The integration injects attributes, creates helper entities, computes shading and sun-facing data, and orchestrates all logic in a lightweight, non-destructive architecture.

---

## ✨ Features

- **Mode system**  
  Named modes with icons, colors, lock, and an optional `behavior` field (`auto_shade` or `solar_gain`).

- **Automation lock**  
  Prevents physical moves; requested positions are stored in memory until unlocked.

- **Position memory (persistent)**  
  Automatically saved when changing mode. Stored in `.storage/cover_extender.memory`.

- **Autonomous solar shading**  
  Computes optimal cover position based on sun azimuth, elevation, facade geometry, and shade configuration.

- **Solar gain optimization**  
  Temperature‑ and weather‑aware auto‑positioning to capture or block heat.

- **Attribute injection**  
  `facade`, `modes`, `auto_shade`, `sun_facing`, and `memory` are added to each cover entity.

- **Optional binary sensors**  
  `sun_facing`, `auto_shade`, and `solar_gain` can be exposed as binary sensors via `show_entities`.

- **Dynamic entity creation**  
  Selects, switches, and binary sensors appear/disappear automatically after reload.

- **Hot reload**  
  Reload YAML config without restarting Home Assistant.

- **Command throttling**  
  All physical cover commands are queued with a configurable delay (default 150 ms) to prevent hardware saturation.

- **HA bus events**  
  `cover_extender_mode_changed`, `cover_extender_memory_saved`, and `cover_extender_shade_applied` are fired automatically, enabling external automations to react to Cover Extender state changes.

---

## 📦 Installation

1. Copy the folder `cover_extender/` into:
   ```
   custom_components/
   ```

2. Add to `configuration.yaml`:
   ```yaml
   cover_extender:
     source: yaml_entities/covers_config.yaml
   ```

3. Restart Home Assistant.

---

# 🧾 Configuration

All configuration lives inside the YAML file referenced by `source:`.

## Example

```yaml
facades:
  south:
    azimuth: 180
  east:
    azimuth: 90

cover_extender_modes:
  Day:
    icon: mdi:white-balance-sunny
    color: orange
  Shade:
    icon: mdi:sun-clock
    color: amber
    lock: true
    behavior: auto_shade
  Solar:
    icon: mdi:sun-thermometer
    color: "#FF8F00"
    lock: true
    behavior: solar_gain

cover.living_room:
  facade: south
  modes:
    Day: 40
    Shade: null
    Solar: null

  shade:
    enable: true
    distance: 0.4
    max_height: 1.8
    min_height: 0.0
    degrees: 90
    max_elevation: 90
    min_elevation: 5
    minimum_position: 15
    default_position: 100
    change_threshold: 5
    time_out: 2

  solar_gain:
    enable: true
    position_solar: 80
    position_cold: 10

show_entities:
  sun_facing: true
  auto_shade: true
  solar_gain: true

command_interval: 0.3   # optional — seconds between cover commands, default 0.15
```

---

# 🗂️ Configuration Structure

## 1. `facades`
Defines the facade orientation in degrees.

```yaml
facades:
  south:
    azimuth: 180
```

Used in sun-facing calculations.

---

## 2. `cover_extender_modes`
Defines global mode metadata.

```yaml
cover_extender_modes:
  ModeName:
    icon: mdi:icon
    color: "#RRGGBB"
    lock: true/false
    behavior: auto_shade | solar_gain | null
    hidden: true/false
```

The `behavior` field is **optional** (defaults to `null`) and determines which automation switch is activated when the mode is applied:

| `behavior` value | Effect |
|---|---|
| `auto_shade` | Turns on `switch.<cover>_auto_shade` (+ lock) |
| `solar_gain` | Turns on `switch.<cover>_auto_solar_gain` (+ lock) |
| `null` / absent | Turns off both automation switches |

`auto_shade` and `solar_gain` are mutually exclusive — a mode can only activate one at a time.

Notes:
- `hidden` prevents the mode from appearing in the global select entity.
- Colors are not validated — any string is accepted.

---

## 3. Per-cover configuration

```yaml
cover.<entity>:
  facade: south
  modes:
    ModeName: <0‑100 | null | entity_id>
  angle_left: 85.0
  angle_right: 85.0
  entity_picture: http://...
  exclusion: [entity_id, ...]
  shade: {...}
  solar_gain: {...}
```

### Mode positions:
- Integer → fixed position
- `null` → no fixed position (used with `behavior: auto_shade` or `behavior: solar_gain` modes)
- Entity ID → dynamically read numeric position

### `exclusion`
A list of entity IDs (typically `binary_sensor`, `input_boolean`, or `switch`) that block physical movement of the cover when any of them is `on`.

```yaml
cover.living_room:
  exclusion:
    - binary_sensor.window_living_room_open
```

When an exclusion entity is `on`:

- **Mode apply** — the target position is saved to memory instead of being sent to the cover.
- **Lock release** — the stored memory is not applied; the cover stays put.

As soon as all exclusion entities return to `off`, the next mode change or manual lock release will apply the memorized position normally.

**Typical use case:** prevent a cover from moving while a window is open.

---

# 🌞 Sun Facing

The attribute `sun_facing` is injected into each cover and automatically updated whenever:

- the sun's state changes  
- the cover updates  
- configuration reloads

Computation uses:

- facade azimuth  
- per-cover `angle_left` / `angle_right`  
- sun azimuth & elevation

---

# 🌓 Autonomous Solar Shading

Activated when:

- `shade.enable: true`  
- AND `switch.<cover>_auto_shade` is ON  
- (usually turned ON automatically by a mode with `behavior: auto_shade`)

Shading uses:

```
(distance / cos(gamma)) * tan(alpha)
```

And respects:

- sun FOV (`degrees`, `min_elevation`, `max_elevation`)
- `minimum_position`
- `default_position`
- `time_out`
- `change_threshold`

---

# 🌡️ Solar Gain Optimization

Active when:

- `solar_gain.enable: true`
- AND `switch.<cover>_auto_solar_gain` is ON
- (usually turned ON automatically by a mode with `behavior: solar_gain`)

Behavior:

- If temperature ≥ threshold → no action  
- Else if sun_facing & weather good → `position_solar`  
- Else → `position_cold`

Global config (top level):

```yaml
solar_gain:
  temperature_entity: sensor.outdoor_temp
  temperature_threshold: 19.0
  weather_entity: weather.home
  good_conditions:
    - sunny
    - partlycloudy
```

---

# 🔐 Mode System (Actual Behavior)

```
           ┌──────────────┐
           │     MODE     │
           └──────────────┘
                   │
                   ▼
        ┌────────────────────┐
        │ Behavior context   │
        │ - lock             │
        │ - auto_shade       │
        │ - solar_gain       │
        └────────────────────┘
                   │
                   ▼
        ┌────────────────────┐
        │ Target position ?  │
        └────────────────────┘
          YES│          │NO
             ▼          ▼
 ┌──────────────────┐   ┌─────────────────────┐
 │ Target position  │   │ No direct movement  │
 │ (fixed / entity) │   │ Automation only     │
 └──────────────────┘   └─────────────────────┘
             │
             ▼
       ┌──────────────────────────────┐
       │ Movement allowed ?           │
       │ (lock OFF & no exclusion ?)  │
       └──────────────────────────────┘
          │ YES                     │ NO
          ▼                         ▼
 ┌──────────────────┐     ┌────────────────────┐
 │ Move cover       │     │ Do NOT move cover  │
 │ physically       │     └────────────────────┘
 └──────────────────┘              |
             └─────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ Position stored  │
              │ in memory        │
              └──────────────────┘
```

When a mode is applied:

1. **Current position is always saved to memory**  

2. Apply `lock:` property

3. Apply `behavior:` (turns on/off `auto_shade` and `solar_gain` switches)

4. Determine position:
   - fixed position in mode  
   - OR restore memory if previous mode was not locked  
   - OR no move (for `behavior: solar_gain` — position determined by solar gain logic)

5. If `behavior: solar_gain` → immediate solar gain evaluation

---

# 🧱 Injected Attributes

Injected into each cover entity:

- `facade`
- `modes`
- `auto_shade`
- `sun_facing`
- `memory` (if present)

Attributes update on each state change.

---

## 5. `command_interval` *(optional)*

Minimum delay in seconds between two consecutive physical cover commands.

```yaml
command_interval: 0.3   # default: 0.15
```

Useful when your hardware bridge rejects commands that arrive too close together. Applies globally to all covers. Takes effect immediately after a `cover_extender.reload`.

---

# 🆕 Optional Binary Sensors

Enabled with:
```yaml
show_entities:
  sun_facing: true
  auto_shade: true
  solar_gain: true
```

Creates:

- `binary_sensor.<cover>_sun_facing`
- `binary_sensor.<cover>_auto_shade`
- `binary_sensor.<cover>_solar_gain`

---

# 🧰 Entities Created Per Cover

| Entity | Purpose |
|--------|---------|
| `select.mode_<cover>` | Choose mode |
| `switch.<cover>_lock` | Automation lock |
| `switch.<cover>_auto_shade` | Autonomous shading (if `shade.enable: true`) |
| `switch.<cover>_auto_solar_gain` | Solar gain toggle (if `solar_gain.enable: true`) |
| `binary_sensor.<cover>_sun_facing` | Optional (`show_entities`) |
| `binary_sensor.<cover>_auto_shade` | Optional (`show_entities`) |
| `binary_sensor.<cover>_solar_gain` | Optional (`show_entities`) |

Global selector:

- `select.cover_extender_modes`

---

# 🔧 Services

### `cover_extender.set_cover_position`
Lock-aware positioning.

### `cover_extender.open_cover` / `close_cover`
Lock-aware 100% / 0%.

### `cover_extender.apply_mode`
Applies a mode to one or more covers.

Returns:
```json
{ "applied": [...], "skipped": [...] }
```

### `cover_extender.apply_memory`
Force applying stored memory.

### `cover_extender.compute_shade_position`
Returns:
```json
{ "position": <int>, "should_update": <bool> }
```

### `cover_extender.get_mode_position`
Reads configured mode position.

### `cover_extender.reload`
Reloads YAML configuration without restarting Home Assistant.

---

# 🚨 Command Throttling

All physical `cover.*` commands are routed through a global queue and executed with a minimum delay between commands (default 150 ms, configurable via `command_interval`).

Switch toggles are **not** throttled.

---

# 📡 HA Bus Events

Cover Extender fires the following events on the HA event bus, allowing external automations to react without polling entities:

| Event | Fired when | Payload |
|---|---|---|
| `cover_extender_mode_changed` | A mode is applied to a cover | `entity_id`, `mode`, `from_mode`, `position` |
| `cover_extender_memory_saved` | A position is stored in or cleared from memory | `entity_id`, `position` (`null` = cleared) |
| `cover_extender_shade_applied` | Auto-shade computes and enqueues a new position | `entity_id`, `position` |

Example automation trigger:

```yaml
trigger:
  - platform: event
    event_type: cover_extender_mode_changed
    event_data:
      mode: Night
```

---

# 🧪 Example Automation

```yaml
service: cover_extender.apply_mode
data:
  entity_id:
    - cover.living_room
  mode: Shade
```
