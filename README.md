# Cover Extender

Cover Extender is a Home Assistant custom integration that enriches existing cover (blind/shutter) entities with advanced automation features: mode management, automation lock, persistent memory, autonomous solar shading, and solar gain optimization — all without replacing or duplicating your cover entities.

The integration injects attributes, creates helper entities, computes shading and sun-facing data, and orchestrates all logic in a lightweight, non-destructive architecture.

---

## 🧠 Philosophy of the Component

Cover Extender is built on a simple idea: **automation should enhance control, not replace it**.

Rather than introducing new cover entities or abstracting your hardware behind opaque logic, Cover Extender **extends what already exists**. Your original `cover.*` entities remain the single source of truth. The integration adds intelligence *around* them — never *over* them.

---

### 🎯 Intention First, Mechanics Second

Traditional automations often bind **conditions directly to actions**:

> *If sun elevation > X → move cover to Y*

While effective, this approach quickly becomes hard to reason about, override, or debug.

Cover Extender takes a different path:
- You express **intent** using **modes**
- Each mode defines *context* (lock, behavior, strategy)
- Automation logic only runs **when explicitly allowed**

A mode answers the question:

> *"What is this cover supposed to do right now?"*

Not:

> *"Which automation happens to fire?"*

---

### 🧩 Non‑Destructive by Design

Cover Extender follows a strict rule:

> **It never replaces, clones, or takes ownership of your covers.**

Instead, it:
- injects attributes
- creates helper entities (selects, switches, sensors)
- orchestrates commands through a controlled layer

At any moment:
- You can bypass Cover Extender and control the cover manually
- A reboot or reload never corrupts native cover state
- Removing the integration restores a clean system

Your hardware remains autonomous. Cover Extender is optional intelligence.

---

### 🔐 Safety Over Surprise

Unintended physical movement is one of the most common frustrations with cover automations.

Cover Extender treats this as a **first‑class concern**:

- **Lock** prevents movement — not just automation
- **Exclusion entities** (e.g. open windows) block commands safely
- **Target positions are remembered**, not lost
- Nothing "catches up" later without your consent

If a cover does not move, it is never a mystery:

> *It is either locked, excluded, or waiting in memory.*

---

### 🧠 Memory Instead of Guesswork

When automation is paused, many systems simply… give up.

Cover Extender does not.

- Every mode change saves the current position
- Blocked movements are intentionally memorized
- Unlocking applies memory only when movement is safe

This creates **continuity of intent**:

> *"I wanted this position — apply it when possible."*

Not:

> *"Automation failed, state lost."*

---

### 🌞 Sun Automation as a Strategy, Not a Reflex

Solar logic in Cover Extender is **deliberate, not reactive**.

- Sun data is always computed
- But actions only occur when:
  - the corresponding automation switch is ON
  - usually enabled by a mode

There is no background process constantly fighting the user.  
Sun automation is:
- scoped
- reversible
- visible

You decide *when* the sun matters.

---

### 🧠 Explicit Is Better Than Clever

Cover Extender intentionally avoids:
- hidden assumptions
- implicit behavior chains
- "smart" actions with no clear trigger

Instead, it favors:
- explicit modes
- visible switches
- deterministic state changes
- Home Assistant events for external orchestration

Everything it does is:
- observable
- debuggable
- reversible

---

### 🤝 A Good Home Assistant Citizen

Cover Extender respects Home Assistant's ecosystem:

- Full UI configuration via config flow and subentries
- Hot reload, no restart required
- Native entities, services, and events
- Plays well with dashboards and automations
- No cloud, no polling hacks, no side effects

It aims to feel like:

> *"Something Home Assistant could have shipped — if covers were modes‑aware."*

---

### ✅ In One Sentence

**Cover Extender does not automate covers for you — it gives you the tools to express intent, safely, predictably, and on your own terms.**

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

- **Cover templates**  
  Reusable angle + shade/solar-gain settings shared across multiple covers. Editing a template propagates automatically to every cover that references it.

- **Attribute injection**  
  `facade`, `modes`, `auto_shade`, `sun_facing`, and `memory` are added to each cover entity.

- **Optional binary sensors**  
  `sun_facing`, `auto_shade`, and `solar_gain` can be exposed as binary sensors.

- **Dynamic entity creation**  
  Selects, switches, and binary sensors appear/disappear automatically after reload.

- **Hot reload**  
  Reload configuration without restarting Home Assistant.

- **Command throttling**  
  All physical cover commands are queued with a configurable delay (default 150 ms) to prevent hardware saturation.

- **HA bus events**  
  `cover_extender_mode_changed`, `cover_extender_memory_saved`, and `cover_extender_shade_applied` are fired automatically, enabling external automations to react to Cover Extender state changes.

---

## 📦 Installation

1. Copy the `cover_extender/` folder into `custom_components/`.

2. Restart Home Assistant.

3. Go to **Settings → Integrations → Add integration** and search for **Cover Extender**.

4. The setup wizard opens. Configure your facades, modes, cover templates and covers directly from the UI.

> Requires Home Assistant 2024.11 or later.

---

# 🧾 Configuration

All configuration is managed through **Settings → Integrations → Cover Extender** using subentries.

## Subentry types

| Type | Description |
|---|---|
| **Facade** | A building orientation with a compass azimuth (°). |
| **Mode** | A named operating mode: icon, color, lock flag, automation behavior. |
| **Cover template** | Shared angle + shade/solar-gain settings reused across covers. |
| **Cover** | A cover profile: entity, facade, modes, automation, exclusion. |
| **Global settings** | Command interval, binary sensor visibility, solar-gain global config. |

---

## Facades

A facade defines the compass orientation of a wall in degrees (0 = North, 180 = South). It is referenced by each cover to compute sun-facing status and shading geometry.

---

## Modes

Each mode defines the context in which a cover operates:

| Field | Description |
|---|---|
| `name` | Unique identifier (e.g. Day, Shade, Night). |
| `icon` | MDI icon name (e.g. `mdi:white-balance-sunny`). |
| `color` | Hex color for dashboards (e.g. `#FF8F00`). |
| `lock` | Whether the cover is locked in this mode. |
| `behavior` | `auto_shade`, `solar_gain`, or none. Determines which automation switch is activated. |
| `hidden` | If `true`, the mode is excluded from the global mode selector. |

`auto_shade` and `solar_gain` are mutually exclusive per mode.

---

## Cover templates

A **cover template** groups the physical-window parameters that are identical for several covers, avoiding repetition. It acts as a **live reference**: editing a template immediately propagates its values to all covers using it.

**Template parameters:**

| Parameter | Description |
|---|---|
| `name` | Unique template name. |
| `angle_left` / `angle_right` | Sun azimuth offset (°) relative to the facade normal. |
| Shade parameters | `distance`, `max_height`, `min_height`, `degrees`, `min/max_elevation`, positions, threshold, timeout. |
| Solar-gain parameters | `position_cold`, `position_solar`. |

**When to use a template:**  
If two or more covers have the same physical window geometry and the same shading/solar-gain parameters, create one template and reference it from each cover. If a cover has unique characteristics, configure it without a template.

---

## Covers

Each cover profile links a `cover.*` entity to its facade, modes and automation settings.

### Identity step
- Cover entity, optional image URL, facade, optional cover template, exclusion entities.

### Angles step *(only when no template)*
- `angle_left` / `angle_right`: sun azimuth offsets relative to the facade normal (0–90°).

### Mode selection and configuration
- Choose which modes apply to this cover.
- For each mode, set the target position: fixed integer (0–100), `auto` (no fixed position, used with behavior modes), or an entity ID read at runtime.

### Automation step *(only when no template)*
All shade and solar-gain parameters for this cover:

**Shade (`shade`):**

| Parameter | Default | Description |
|---|---|---|
| `enable` | `false` | Activate autonomous shading. |
| `distance` | `0.3` m | Horizontal distance to the obstacle (e.g. balcony depth). |
| `max_height` | `1.5` m | Maximum shadow height to cast on the window. |
| `min_height` | `0.0` m | Minimum shadow height; below this, the cover opens. |
| `degrees` | `90` ° | Azimuth window within which the sun triggers shading. |
| `max_elevation` | `90` ° | Above this elevation the cover is not moved. |
| `min_elevation` | `5` ° | Below this elevation the cover is not moved. |
| `minimum_position` | `10` % | Floor position during shading. |
| `default_position` | `100` % | Position used when sun is outside the window. |
| `change_threshold` | `5` % | Minimum position delta before issuing a new command. |
| `time_out` | `1` min | Stability delay before applying a new shading position. |

**Solar gain (`solar_gain`):**

| Parameter | Default | Description |
|---|---|---|
| `enable` | `false` | Activate solar-gain optimization. |
| `position_cold` | `0` % | Position when conditions are cold or unfavorable. |
| `position_solar` | `100` % | Position when sun is facing and conditions are favorable. |

---

## Global settings

| Field | Description |
|---|---|
| `command_interval` | Delay (s) between consecutive cover commands. Default `0.15`. |
| `show_sun_facing` | Create `binary_sensor.<cover>_sun_facing` for each cover. |
| `show_auto_shade` | Create `binary_sensor.<cover>_auto_shade`. |
| `show_solar_gain` | Create `binary_sensor.<cover>_solar_gain`. |
| Temperature entity | Sensor used to evaluate the solar-gain temperature threshold. |
| Temperature threshold | Static float **or** `input_number` entity ID, resolved at runtime. |
| Weather entity | `weather.*` entity used to check conditions. |
| Good conditions | Weather states that allow solar-gain positioning. |

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

- shade is enabled on the cover (or its template)  
- AND `switch.<cover>_auto_shade` is ON  
- (usually turned ON automatically by a mode with `behavior: auto_shade`)

Shading uses:

```
(distance / cos(gamma)) * tan(alpha)
```

And respects: sun FOV, `minimum_position`, `default_position`, `time_out`, `change_threshold`.

---

# 🌡️ Solar Gain Optimization

Active when:

- solar gain is enabled on the cover (or its template)
- AND `switch.<cover>_auto_solar_gain` is ON
- (usually turned ON automatically by a mode with `behavior: solar_gain`)

Behavior:

- If temperature ≥ threshold → no action  
- Else if sun_facing & weather good → `position_solar`  
- Else → `position_cold`

---

# 🔐 Mode System (Actual Behavior)

```
                     ┌────────────────────────┐
                     │        APPLY MODE      │
                     └────────────────────────┘
                                  │
                                  ▼
                  ┌─────────────────────────────────┐
                  │ Save CURRENT position to memory │
                  └─────────────────────────────────┘
                                  │
                                  ▼
         ┌─────────────────────────────────────────────┐
         │ Apply mode context                          │
         │ - lock on/off                               │
         │ - behavior: auto_shade / solar_gain / none  │
         │ - toggle automation switches                │
         └─────────────────────────────────────────────┘
                                  │
                                  ▼
                  ┌─────────────────────────────────┐
                  │ Is a target position defined ?  │
                  └─────────────────────────────────┘
                     YES │                       │ NO
                         ▼                       ▼
        ┌───────────────────────────┐   ┌────────────────────────┐
        │ Fixed / entity / memory   │   │ No direct movement     │
        │ target position resolved  │   │ Automation only        │
        └───────────────────────────┘   └────────────────────────┘
                         │
                         ▼
             ┌────────────────────────────────────┐
             │ Is physical movement allowed ?     │
             │ - lock OFF ?                       │
             │ - no exclusion entity ON ?         │
             └────────────────────────────────────┘
                   │ YES                      │ NO
                   ▼                          ▼
        ┌────────────────────────┐   ┌───────────────────────────┐
        │ Send cover command     │   │ Do NOT move cover         │
        │ (throttled queue)      │   └───────────────────────────┘
        └────────────────────────┘               │
                                                 ▼
                                     ┌─────────────────────────┐
                                     │ Store target in memory  │
                                     └─────────────────────────┘
```
# 🔐 Lock System (Actual Behavior)
```
            ┌──────────────────────────┐
            │        UNLOCK            │
            │  (switch.lock → OFF)     │
            └──────────────────────────┘
                         │
                         ▼
     ┌────────────────────────────────────┐
     │ Is a memory position stored ?      │
     └────────────────────────────────────┘
                 │ YES              │ NO
                 ▼                  └────────────┐
 ┌─────────────────────────────────────┐         |
 │ Are exclusion entities all OFF ?    │         |
 └─────────────────────────────────────┘         |
               │ YES                 │ NO        |
               ▼                     ▼           ▼        
┌────────────────────────────┐   ┌────────────────────────────┐
│ Apply memorized position   │   │ DO NOTHING                 │
│ → physical move allowed    │   │ Memory kept                │
└────────────────────────────┘   └────────────────────────────┘
```

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

# 🧰 Entities Created Per Cover

| Entity | Purpose |
|--------|---------|
| `select.mode_<cover>` | Choose mode |
| `switch.<cover>_lock` | Automation lock |
| `switch.<cover>_auto_shade` | Autonomous shading switch |
| `switch.<cover>_auto_solar_gain` | Solar gain toggle |
| `binary_sensor.<cover>_sun_facing` | Optional (global settings) |
| `binary_sensor.<cover>_auto_shade` | Optional (global settings) |
| `binary_sensor.<cover>_solar_gain` | Optional (global settings) |

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
Reloads configuration without restarting Home Assistant.

---

# 🚨 Command Throttling

All physical `cover.*` commands are routed through a global queue and executed with a minimum delay between commands (default 150 ms, configurable via global settings).

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
