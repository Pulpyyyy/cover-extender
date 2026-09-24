# Cover Extender

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Release](https://img.shields.io/github/v/release/Pulpyyyy/cover-extender)](https://github.com/Pulpyyyy/cover-extender/releases)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.1%2B-blue)

🇫🇷 [Lire en français](https://github.com/Pulpyyyy/cover-extender/blob/main/README.fr.md)

Cover Extender is a Home Assistant integration that adds [modes](#modes), a [lock with position memory](#lock-and-memory), [exclusions](#exclusions) and sun automation ([shading](#autonomous-shading), [solar gain](#solar-gain)) to the covers you already have, all configured from an [admin panel](#the-admin-panel) with a modes × covers matrix, in English or French.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Pulpyyyy&repository=cover-extender&category=integration)

![Matrix tab](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-matrix.png)

---

## Contents

- [Design philosophy](#design-philosophy)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Key concepts](#key-concepts)
- [The admin panel](#the-admin-panel)
- [Reference](#reference)
- [How it works](#how-it-works)
- [FAQ and troubleshooting](#faq-and-troubleshooting)
- [Uninstall](#uninstall)
- [Support and contributing](#support-and-contributing)

---

## Design philosophy

Cover Extender is built on a simple idea: **automation should enhance control, not replace it**.

### 🎯 Intention first, mechanics second

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

### 🧩 Non-destructive by design

Cover Extender follows a strict rule:

> **It never replaces, clones, or takes ownership of your covers.**

Rather than abstracting your hardware behind opaque logic, it **extends what already exists**: your `cover.*` entities remain the single source of truth, and the integration adds intelligence *around* them, never *over* them. It:

- injects attributes
- creates helper entities (selects, switches, sensors)
- orchestrates commands through a controlled layer

At any moment:

- You can bypass Cover Extender and control the cover manually
- A reboot or reload never corrupts native cover state
- Removing the integration restores a clean system

Your hardware remains autonomous. Cover Extender is optional intelligence.

### 🔐 Safety over surprise

Unintended physical movement is one of the most common frustrations with cover automations.

Cover Extender treats this as a **first-class concern**:

- **Lock** holds back the commands sent through Cover Extender and remembers them instead
- **Exclusion entities** (e.g. open windows) block every move Cover Extender would make
- Nothing catches up later that you did not ask for

If a cover does not move, it is never a mystery:

> *It is either locked, excluded, or waiting in memory.*

### 🧠 Memory instead of guesswork

When automation is paused, many systems simply… give up.

Cover Extender does not.

- Every change to a locked mode saves the current position
- Blocked movements are intentionally memorized
- Unlocking applies memory only when movement is safe

This creates **continuity of intent**:

> *"I wanted this position: apply it when possible."*

Not:

> *"Automation failed, state lost."*

### 🌞 Sun automation as a strategy, not a reflex

Solar logic in Cover Extender is **deliberate, not reactive**.

- Sun data is always computed
- But actions only occur when:
  - the corresponding automation switch is on
  - usually enabled by a mode

There is no background process constantly fighting the user. Sun automation is:

- scoped
- reversible
- visible

You decide *when* the sun matters.

### 🔍 Explicit is better than clever

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

### 🤝 A good Home Assistant citizen

Cover Extender respects Home Assistant's ecosystem:

- Full UI configuration via an embedded admin panel
- Hot reload, no restart required
- Native entities, services, and events
- Plays well with dashboards and automations
- No cloud, no polling hacks

It aims to feel like:

> *"Something Home Assistant could have shipped, if covers were mode-aware."*

### ✅ In one sentence

**Cover Extender does not automate covers for you: it gives you the tools to express intent, safely, predictably, and on your own terms.**

---

## Installation

Requires **Home Assistant 2026.1** or later, and covers that support `set_cover_position` (a position from 0 to 100).

### With HACS (recommended)

Cover Extender is not in the HACS default list yet: add it as a custom repository.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Pulpyyyy&repository=cover-extender&category=integration)

Or by hand:

1. In Home Assistant, open **HACS**, then the **⋮** menu (top right) and **Custom repositories**.
2. Repository: `https://github.com/Pulpyyyy/cover-extender`, type: **Integration**, then **Add**.
3. Search for **Cover Extender** in HACS, open it and click **Download**.
4. **Restart** Home Assistant.

### Manual

1. Download the latest [release](https://github.com/Pulpyyyy/cover-extender/releases).
2. Copy the `custom_components/cover_extender/` folder into the `custom_components/` folder of your Home Assistant configuration (create it if needed).
3. **Restart** Home Assistant.

### Add the integration

[![Open your Home Assistant instance and start setting up Cover Extender.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=cover_extender)

Or go to **Settings → Devices & services → Add integration** and search for **Cover Extender**. There is nothing to fill in: the integration is created and everything else happens in the admin panel.

**Upgrading from 2.x:** the stored configuration migrates automatically at first startup. The migration is one-way: going back to 2.x afterwards is refused rather than risking corruption.

---

## Quick start

This walk-through sets up one cover with two modes, *Day* (open) and *Night* (closed). It takes about five minutes.

1. **Open the panel.** Click **Cover Extender** in the sidebar, or the button on the integration page, or go to `http://<your-ha>:8123/cover-extender`.
2. **Create a facade.** In **Settings → Facades**, click **Add a facade**. Name it (e.g. *South*) and set its **azimuth**, the direction the windows face: 0° = north, 90° = east, 180° = south, 270° = west. A compass app held flat against the window, looking out, gives you the value.
3. **Create two modes.** In **Modes**, click **Add a mode** twice: *Day* and *Night*. Leave **Behavior** on *None* for both. Tick **Lock the covers** on *Night* if you want remote commands made through Cover Extender to wait until morning.
4. **Add your cover.** In **Covers**, click **Add a cover**, pick the `cover.*` entity and the *South* facade, then **Save**.
5. **Set the positions.** In **Matrix**, click the empty *Day* cell on your cover: it links the mode. Choose **Fixed** and 100 %. Do the same for *Night* at 0 %, then **Save**. Positions follow Home Assistant's convention: **0 = closed, 100 = open**.
6. **Try it.** A new entity `select.mode_<your_cover>` appeared. Change it from *Day* to *Night*: the cover closes.

### Next steps

- Switch modes from your automations with the [`cover_extender.apply_mode`](#cover_extenderapply_mode) action, e.g. *Night* at sunset:

  ```yaml
  triggers:
    - trigger: sun
      event: sunset
  actions:
    - action: cover_extender.apply_mode
      target:
        area_id: living_room
      data:
        mode: Night
  ```

- Add an [exclusion entity](#exclusions) (a window contact) so that the cover never closes on an open window.
- Try [shading](#autonomous-shading): create a mode with the *Shading* behavior and fill the cover's **Geometry** and **Shading** sections.
- Use the [global selector](#the-global-mode-selector) to switch every cover at once from a dashboard.

---

## Key concepts

### Modes

A mode says *what the cover should be doing right now*. Each mode has a name, icon and color, and optionally:

- **Lock the covers**: while the mode is on, the cover is [locked](#lock-and-memory).
- **Behavior**: *None* (each cover gets its own position from the matrix), *Shading* (the position is computed from the sun, see [autonomous shading](#autonomous-shading)) or *Solar gain* (see [solar gain](#solar-gain)).
- **Hide from the selector**: the mode stays usable by automations but does not show in the global selector.

A mode only applies to the covers it is linked to (a cell in the matrix). For each linked cover, the matrix sets what happens when the mode turns on:

| Choice | Effect |
|---|---|
| **Fixed** | The cover goes to this position (0-100). |
| **Entity** | The cover follows the value of an `input_number` or `number` entity, live, as long as the mode is on. |
| **None** | The cover does not move. If the previous mode was locked and this one is not, the memorized position is restored. |
| **Auto** (behavior modes only) | The position is computed by the behavior. Choosing Fixed or Entity instead overrides the computation for this cover only. |

Each cover gets a `select.mode_<cover>` entity listing its linked modes: changing it applies the mode.

### Lock and memory

The lock is a switch per cover, `switch.<cover>_lock`. Modes turn it on and off, and you can toggle it by hand.

While it is on, **positions requested through Cover Extender are stored in memory instead of moving the cover**: the [`set_cover_position`, `open_cover` and `close_cover` actions](#actions) of Cover Extender, and the Entity positions of the active mode.

- Entering a locked mode from an unlocked one **saves the current position** to memory.
- Leaving it for an unlocked mode without a position (None) **restores** that position.
- Turning the lock off by hand **applies the memory** (unless an exclusion is active).
- The memorized position shows as the `memory` attribute of the cover.

> [!IMPORTANT]
> The lock only filters what goes through Cover Extender. A remote control, the cover's own card or a native `cover.set_cover_position` still move the cover. That is deliberate: Cover Extender never takes your covers away from you.

A *Shading* or *Solar gain* mode always locks the cover, so that its computed moves do not erase the position you had before. The only exception is a cover that overrides the mode with its own Fixed or Entity position: the mode's own lock setting applies to it.

### Exclusions

In the cover editor, **Exclusion entities** lists entities that block the cover while one of them is `on`: typically a window or door contact (`binary_sensor`), or an `input_boolean` for "do not disturb".

While an exclusion is on:

- a mode change or a Cover Extender action does not move the cover: its position **waits, and is applied as soon as the last exclusion turns off**. Close the window and the *Night* mode you chose meanwhile closes the cover;
- shading and solar gain skip the cover, and catch up as soon as the last exclusion turns off;
- turning the lock off does not apply the memory.

Only the latest request waits: a new mode replaces it. If the cover got locked meanwhile, an action's position stays in memory until the unlock, as any command made while locked. A pending position does not survive a restart of Home Assistant.

### Facades and orientation

A **facade** is a wall orientation, shared by all the covers on that wall. Its **azimuth** is the direction the windows face, looking out: 0° = north, 90° = east, 180° = south, 270° = west.

Each cover then decides when the sun is **facing** it with two angles, measured from the facade direction as you look out of the window:

```
                  facade direction (e.g. 180° = south)
                               ▲
         angle to the left     │     angle to the right
        (towards the east       │      (towards the west
         for a south facade)   │       for a south facade)
                  ╲            │            ╱
                   ╲           │           ╱
                    ╲          │          ╱
                     ╲         │         ╱
      ═══════════════════ window (inside below) ═══════════════
```

The sun faces the cover when its azimuth lies between *facade − angle to the left* and *facade + angle to the right*, and it is at least 3° above the horizon. The defaults (85° each side) cover almost the whole half-plane in front of the wall; narrow them for a window set deep in the wall or flanked by a neighbour's building. The result is the `sun_facing` attribute of the cover, used by solar gain.

### Templates

Several windows of the same size, on the same kind of wall, share their geometry and shading settings. A **template** holds those values once; each cover that uses it inherits them and only stores what it changes (shown as *overrides* in the editor). Editing the template updates every cover that uses it.

### Autonomous shading

Shading keeps direct sunlight from reaching further into the room than you decide. When the sun is in front of the window, the cover is lowered just enough; when it is not, the cover goes to its default position.

It runs when all of these hold:

- **Automatic shading enabled** is ticked on the cover (or its template), which creates `switch.<cover>_auto_shade`;
- that switch is on, which a mode with the *Shading* behavior does for you;
- no exclusion is active.

The position is recomputed at every update of `sun.sun` (every few minutes during the day). A new command is only sent when it differs from the current position by at least the **change threshold**, and when the cover has not moved (for any reason) during the last **time-out** minutes, so that a manual adjustment is respected for a while.

The settings, in the cover's **Geometry** and **Shading** sections:

| Setting | Default | Meaning |
|---|---|---|
| Distance from the cover | `0.4` m | How far into the room direct sunlight may reach, measured on the floor from the window. Smaller = the cover closes more. |
| Maximum height | `1.8` m | Height of the cover's bottom edge when fully open (100 %), usually the top of the window. |
| Minimum height | `0.0` m | Height of the bottom edge when fully closed (0 %): 0 for a French window, the sill height for a window. |
| Angular aperture | `90` ° | The sun counts as "in front" when its azimuth is within ± this angle of the facade direction. |
| Minimum / maximum elevation | `5` / `90` ° | Outside this range of sun heights, the cover goes to its default position. |
| Minimum position | `15` % | Shading never closes further than this. |
| Default position | `100` % | Position when the sun is not in front of the window. |
| Change threshold | `5` % | Smaller changes are ignored, to spare the motor. |
| Time-out | `2` min | Minimum time since the last movement of the cover (from any source) before shading moves it again. Entering a shading mode ignores it. |

The height of the bottom edge is `distance / cos(γ) × tan(α)`, where α is the sun's elevation and γ the angle between the sun and the facade direction, then converted to a percentage between the minimum and maximum heights.

### Solar gain

Solar gain is a **cold-weather** feature: let the sun heat the room when it can, keep the heat in when it cannot.

It runs when **Solar gain enabled** is ticked on the cover (which creates `switch.<cover>_auto_solar_gain`), that switch is on (a mode with the *Solar gain* behavior does it), and no exclusion is active. Then:

- if the temperature entity is at or above the threshold, **nothing happens** (the cover stays where it is);
- otherwise, if the sun [faces](#facades-and-orientation) the cover and the weather is in the good conditions list, the cover goes to **Position in the sun** (default 100 %);
- otherwise it goes to **Position when cold** (default 0 %).

The temperature entity, threshold and weather entity are shared by all covers (**Settings → General settings**). Without a temperature entity, the temperature check is skipped; without a weather entity, the weather is considered good. The threshold is a number, or an `input_number` so that you can change it from a dashboard. Solar gain is re-evaluated at every change of the sun, the temperature, the threshold or the weather.

### The global mode selector

`select.cover_extender_modes` lists every mode that is not hidden, with its icon and color: it is meant for dashboards.

> [!NOTE]
> Changing it **does not change any cover by itself**. Connect it with an automation:

```yaml
alias: Cover Extender - apply the global mode
triggers:
  - trigger: state
    entity_id: select.cover_extender_modes
    not_from: [unknown, unavailable]
    not_to: [unknown, unavailable]
actions:
  - action: cover_extender.apply_mode
    target:
      # Every cover managed by Cover Extender (they all carry a facade attribute).
      entity_id: >
        {{ states.cover | selectattr('attributes.facade', 'defined')
           | map(attribute='entity_id') | list }}
    data:
      mode: "{{ trigger.to_state.state }}"
```

Covers that are not linked to the chosen mode are left alone.

---

## The admin panel

All configuration lives in the panel at `/cover-extender`. Every value is checked by the server before it is saved. The panel follows your Home Assistant theme ([dark version](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-matrix-dark.png)) and each administrator reads it in their own language (English and French).

| Tab | What it edits |
|---|---|
| **Matrix** | Modes × covers: link modes and set every per-cover position from one grid. |
| **Covers** | The covers: entity, facade, template, exclusions, geometry, shading and solar-gain settings. |
| **Modes** | Icon, color, lock, behavior, visibility. Drag the tiles to reorder: the order drives the mode selectors. |
| **Settings** | Facades, templates, general settings, and a count of the entities the configuration produced. |

### The matrix

Each cell is the position of one mode on one cover. Click a cell to edit it, or an empty cell to link the mode. The popover offers **Fixed** (slider), **Entity** and **None**, plus a one-tick "apply to the other covers of the same facade". Deleting and renaming stay safe: a facade, template or mode still used by covers cannot be deleted, and renames follow everywhere.

On a *Shading* or *Solar gain* mode, cells show `auto`. The same popover can **override the computation for a single cover** with a Fixed or Entity position. Below, *Shade* computes everywhere except on *Office*, pinned at 30 %:

![Overriding an automatic mode for one cover](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/matrix-override.png)

### The other tabs

| | |
|---|---|
| ![Covers tab](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-covers.png) | ![Modes tab](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-modes.png) |

![Settings tab](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-settings.png)

---

## Reference

### Entities

Per cover:

| Entity | Created when | Purpose |
|---|---|---|
| `select.mode_<cover>` | always | Current mode of the cover. Changing it applies the mode. |
| `switch.<cover>_lock` | always | The [lock](#lock-and-memory). |
| `switch.<cover>_auto_shade` | shading enabled on the cover | Turns [shading](#autonomous-shading) on or off. |
| `switch.<cover>_auto_solar_gain` | solar gain enabled on the cover | Turns [solar gain](#solar-gain) on or off. |
| `binary_sensor.<cover>_sun_facing` | option in General settings | The sun faces the cover. |
| `binary_sensor.<cover>_auto_shade` | option in General settings | Shading is enabled on the cover. |
| `binary_sensor.<cover>_solar_gain` | option in General settings | Solar gain is enabled on the cover. |

Global: `select.cover_extender_modes`, see [the global mode selector](#the-global-mode-selector).

Covers are tracked by their entity registry id: renaming a cover, or any of these entities, breaks nothing. After a cover rename, the helper entities keep their old entity_id (standard Home Assistant behavior); rename them by hand if you want matching names.

### Attributes added to each cover

| Attribute | Content |
|---|---|
| `facade` | Name of the cover's facade. |
| `modes` | Linked modes and their position: a number, an entity id, or `null` (None, or computed by the behavior). |
| `auto_shade` | Shading is enabled on the cover. |
| `sun_facing` | The sun faces the cover. |
| `memory` | Memorized position, when there is one. |

### Actions

All actions that take a `target` accept entities, devices, areas and labels.

#### `cover_extender.set_cover_position`

Moves the covers to `position` (0-100), or memorizes it when the cover is locked or excluded.

```yaml
action: cover_extender.set_cover_position
target:
  entity_id: cover.office
data:
  position: 40
```

#### `cover_extender.open_cover` / `cover_extender.close_cover`

Same as `set_cover_position` with 100 or 0.

#### `cover_extender.apply_mode`

Applies `mode` to the target covers. Returns the covers that were changed and those skipped (mode not linked to them).

```yaml
action: cover_extender.apply_mode
target:
  entity_id: [cover.office, cover.living_room]
data:
  mode: Shade
response_variable: result   # optional: {"applied": [...], "skipped": [...]}
```

#### `cover_extender.apply_memory`

Applies the memorized position **even when the cover is locked**, then keeps it in memory.

#### `cover_extender.compute_shade_position`

Returns the shading position computed right now for `entity_id`, without moving anything: `{"position": 35, "should_update": true}`. Useful to tune the settings.

#### `cover_extender.get_mode_position`

Returns the position configured for `mode` on `entity_id`: `{"position": 30}` (a number, an entity id, or `null` for None or a computed position).

#### `cover_extender.reload`

Reloads the configuration. The panel does it on every save; this is only useful from scripts.

### Events

| Event | Fired when | Data |
|---|---|---|
| `cover_extender_mode_changed` | A mode is applied to a cover | `entity_id`, `mode`, `from_mode`, `position` |
| `cover_extender_memory_saved` | A position is stored in or cleared from memory | `entity_id`, `position` (`null` = cleared) |
| `cover_extender_shade_applied` | Shading sends a new position | `entity_id`, `position` |

```yaml
triggers:
  - trigger: event
    event_type: cover_extender_mode_changed
    event_data:
      mode: Night
```

### General settings

| Setting | Meaning |
|---|---|
| Interval between commands | Delay between two commands sent to the covers, default 150 ms. Every move goes through one queue, so that many covers switching at once do not saturate a radio bridge (Somfy RTS, Zigbee...). Switch toggles are not delayed. |
| Temperature entity | Temperature compared with the threshold by solar gain. |
| Threshold entity | Threshold (°) as a number or an `input_number`. Default 19. |
| Weather entity | `weather.*` entity checked by solar gain. |
| Good weather conditions | Weather states that allow solar gain. Default: sunny, partly cloudy. |
| Display | Creates the optional binary sensors listed in [Entities](#entities). |

---

## How it works

### Applying a mode

```
                     ┌────────────────────────┐
                     │        APPLY MODE      │
                     └────────────────────────┘
                                  │
                                  ▼
                  ┌─────────────────────────────────┐
                  │ Unlocked → locked: save the     │
                  │ current position to memory      │
                  └─────────────────────────────────┘
                                  │
                                  ▼
         ┌─────────────────────────────────────────────┐
         │ Apply the mode context                      │
         │ - lock on/off                               │
         │ - shading / solar gain switches on/off      │
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
        │ target position resolved  │   │ (behavior computes it) │
        └───────────────────────────┘   └────────────────────────┘
                         │
                         ▼
             ┌────────────────────────────────────┐
             │ Is an exclusion entity on ?        │
             └────────────────────────────────────┘
                   │ NO                       │ YES
                   ▼                          ▼
        ┌────────────────────────┐   ┌───────────────────────────┐
        │ Send cover command     │   │ Do NOT move the cover     │
        │ (throttled queue)      │   │ Apply it once the last    │
        └────────────────────────┘   │ exclusion turns off       │
                                     └───────────────────────────┘
```

### Turning the lock off by hand

```
            ┌──────────────────────────┐
            │         UNLOCK           │
            │  (switch.lock → off)     │
            └──────────────────────────┘
                         │
                         ▼
     ┌────────────────────────────────────┐
     │ Is a memory position stored ?      │
     └────────────────────────────────────┘
                 │ YES              │ NO
                 ▼                  └────────────┐
 ┌─────────────────────────────────────┐         │
 │ Are exclusion entities all off ?    │         │
 └─────────────────────────────────────┘         │
               │ YES                 │ NO        │
               ▼                     ▼           ▼
┌────────────────────────────┐   ┌────────────────────────────┐
│ Apply memorized position   │   │ Do nothing                 │
│ and clear the memory       │   │ (memory kept)              │
└────────────────────────────┘   └────────────────────────────┘
```

---

## FAQ and troubleshooting

**My cover does not move.** It is one of three things: the cover is **locked** (`switch.<cover>_lock` is on, the requested position is in the `memory` attribute), an **exclusion** entity is on, or the mode has **no position** for this cover (None, or the mode is not linked to it in the matrix). For shading, also check the change threshold and the time-out.

**I moved my cover by hand and it went back on its own.** Shading or solar gain is on. Shading waits for the time-out after any movement, then resumes. To keep your position, switch to a mode without a behavior, or turn `switch.<cover>_auto_shade` off.

**Changing `select.cover_extender_modes` does nothing.** Expected: it is a display selector. See [the global mode selector](#the-global-mode-selector) for the automation that connects it.

**I cannot find the panel.** Open `http://<your-ha>:8123/cover-extender` directly. The panel needs an administrator account. If the sidebar entry is missing, it may be hidden: open your **Profile** and change the sidebar items there.

**`switch.<cover>_auto_shade` does not exist.** Tick **Automatic shading enabled** in the cover's Shading section (or in its template). Same for solar gain.

**The cover closes too much / not enough in shading.** Increase **Distance from the cover** to let more sun in, raise **Minimum position** to keep some light. After each change, [`compute_shade_position`](#cover_extendercompute_shade_position) (in **Developer tools → Actions**) shows the new position without moving the cover.

**How do I get debug logs?** Add this to `configuration.yaml` and restart, or use **Enable debug logging** on the integration page:

```yaml
logger:
  logs:
    custom_components.cover_extender: debug
```

Each decision (lock, exclusion, threshold, time-out) is logged with its reason.

---

## Uninstall

1. **Settings → Devices & services → Cover Extender → ⋮ → Delete.** The helper entities, the added attributes and the stored memory are removed. Your covers are untouched.
2. Remove the integration from HACS (or delete `custom_components/cover_extender/`), then restart Home Assistant.

---

## Support and contributing

- Bugs and feature requests: [GitHub issues](https://github.com/Pulpyyyy/cover-extender/issues). Please include your Home Assistant and Cover Extender versions and the debug logs.
- What changed in each version: [CHANGELOG](https://github.com/Pulpyyyy/cover-extender/blob/main/CHANGELOG.md).
- License: [LICENSE](https://github.com/Pulpyyyy/cover-extender/blob/main/LICENSE).
