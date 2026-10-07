# Cover Extender

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Release](https://img.shields.io/github/v/release/Pulpyyyy/cover-extender)](https://github.com/Pulpyyyy/cover-extender/releases)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.1%2B-blue)

🇫🇷 [Lire en français](https://github.com/Pulpyyyy/cover-extender/blob/main/README.fr.md)

Cover Extender is a Home Assistant integration that adds [modes](#modes) (some of them [timed](#timed-modes)), a [lock with position memory](#lock-and-memory), [exclusions and inhibitions](#exclusions), [morning and evening schedules](#schedules) that follow the sun, and sun automation ([shading](#autonomous-shading), [solar gain](#solar-gain)) to the covers you already have, all configured from an [admin panel](#the-admin-panel) with a modes × covers matrix, in English or French.

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
- **Safety exclusions** (e.g. open windows) block every move Cover Extender would make
- **Inhibitions** (e.g. a guest in the room) do the same, except for a priority mode
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

**Upgrading from 3.x:** 4.0 renames the entities it creates to `<cover>_cx_<function>` (for example `switch.living_room_lock` becomes `switch.living_room_cx_lock`, and `select.mode_living_room` becomes `select.living_room_cx_mode`). Home Assistant keeps their history but does not update your automations, scripts and dashboards: **Settings → Repairs** lists every old and new id so you can replace them. An id you had renamed yourself is left as it was.

---

## Quick start

This walk-through sets up one cover with two modes, *Day* (open) and *Night* (closed). It takes about five minutes.

1. **Open the panel.** Click **Cover Extender** in the sidebar, or the button on the integration page, or go to `http://<your-ha>:8123/cover-extender`.
2. **Create a facade.** In **Settings → Facades**, click **Add a facade**. Name it (e.g. *South*) and set its **azimuth**, the direction the windows face: 0° = north, 90° = east, 180° = south, 270° = west. A compass app held flat against the window, looking out, gives you the value.
3. **Create two modes.** In **Modes**, click **Add a mode** twice: *Day* and *Night*. Leave **Behavior** on *None* for both. Tick **Lock the covers** on *Night* if you want remote commands made through Cover Extender to wait until morning.
4. **Add your cover.** In **Covers**, click **Add a cover**, pick the `cover.*` entity and the *South* facade, then **Save**.
5. **Set the positions.** In **Matrix**, click the empty *Day* cell on your cover: it links the mode. Choose **Fixed** and 100 %. Do the same for *Night* at 0 %, then **Save**. Positions follow Home Assistant's convention: **0 = closed, 100 = open**.
6. **Try it.** A new entity `select.<your_cover>_cx_mode` appeared. Change it from *Day* to *Night*: the cover closes.

### Next steps

- Open and close at the right time with the [schedules](#schedules): a morning and an evening time that follow the sun, and a mode per cover.
- Or switch modes from your own automations with the [`cover_extender.apply_mode`](#cover_extenderapply_mode) action, e.g. *Night* at sunset:

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
- **Priority mode**: the mode passes the [inhibitions](#exclusions) (never the safety exclusions). Typically an *Alarm* mode that must close every cover, guest room included.
- **Timed mode**: the mode only lasts a while (1 minute to 24 hours), see [timed modes](#timed-modes).
- **Hide from the selector**: the mode stays usable by automations but does not show in the global selector.

A mode only applies to the covers it is linked to (a cell in the matrix). For each linked cover, the matrix sets what happens when the mode turns on:

| Choice | Effect |
|---|---|
| **Fixed** | The cover goes to this position (0-100). |
| **Entity** | The cover follows the value of an `input_number` or `number` entity, live, as long as the mode is on. |
| **None** | The cover does not move. If the previous mode was locked and this one is not, the memorized position is restored. |
| **Auto** (behavior modes only) | The position is computed by the behavior. Choosing Fixed or Entity instead overrides the computation for this cover only. |

Each cover gets a `select.<cover>_cx_mode` entity listing its linked modes: changing it applies the mode.

### Lock and memory

The lock is a switch per cover, `switch.<cover>_cx_lock`. Modes turn it on and off, and you can toggle it by hand.

While it is on, **positions requested through Cover Extender are stored in memory instead of moving the cover**: the [`set_cover_position`, `open_cover` and `close_cover` actions](#actions) of Cover Extender, and the Entity positions of the active mode.

- Entering a locked mode from an unlocked one **saves the current position** to memory.
- Leaving it for an unlocked mode without a position (None) **restores** that position.
- Turning the lock off by hand **applies the memory** (unless an exclusion is active).
- The memorized position shows as the `memory` attribute of the cover.

> [!IMPORTANT]
> The lock only filters what goes through Cover Extender. A remote control, the cover's own card or a native `cover.set_cover_position` still move the cover. That is deliberate: Cover Extender never takes your covers away from you.

A *Shading* or *Solar gain* mode always locks the cover, so that its computed moves do not erase the position you had before. The only exception is a cover that overrides the mode with its own Fixed or Entity position: the mode's own lock setting applies to it.

### Schedules

The **Schedules** tab holds the house's **morning opening** and **evening closing**, each switched on or off. At each, every cover applies the mode chosen for it in the table below the chart (or keeps its mode, with *None*). It is a mode change like any other: the lock, the exclusions, the inhibitions and the timed modes apply.

Each time follows the sun over the year, within bounds you set:

- **Max time / min time**: the time on the day the sun rises or sets the latest, and the earliest. In between, the curve follows the sun. Drag the two handles together for a **fixed time** all year.
- **Spring / autumn crossing** (optional): the curve lands exactly on sunrise or sunset that day.
- **Floor ("not before") / ceiling ("not after")**: legal times the schedule never goes past, whatever the sun does.

The chart shows the sun, the curve, today's time and where the cover closes before sunset (or opens before sunrise). Every setting is a field and a handle to drag.

If Home Assistant was down at the time of a schedule, the latest one of the day is applied at startup (never on the very first start). Three entities follow the schedules, on the Cover Extender device:

| Entity | Content |
|---|---|
| `binary_sensor.cx_day` | On between today's opening and closing. Attributes `opening`, `closing`, `next_change`, and `cause`: `time` when the clock reached a schedule, `setting` when a schedule was edited (an automation can ignore the latter). |
| `sensor.cx_morning_opening` | Today's morning opening (timestamp). |
| `sensor.cx_evening_closing` | Today's evening closing (timestamp). |

### Timed modes

A mode with a duration is a parenthesis over the cover's **base mode**, the last mode without a duration the cover was put in. Typically a *Manual* mode of one hour: you take the cover over, and it goes back to what it was doing afterwards.

| What happens | Mode of the cover | Base mode |
|---|---|---|
| The morning automation applies *Day* | Day | **Day** |
| You choose *Manual* (1 h) | Manual | Day |
| Before the hour is up, you choose *Guest* (12 h) | Guest | Day |
| Guest's time is up | Day | Day |
| The evening automation applies *Night* | Night | **Night** |

- **When the time is up**, the cover goes back to its base mode, or to a fixed mode set in the mode's editor (*Manual: 1 h, then Day*). The fixed mode can only be a mode without a duration, so every countdown ends on a mode that starts no other.
- **A mode without a duration chosen meanwhile** applies at once, ends the countdown and becomes the base mode.
- **Choosing the running timed mode again** restarts its countdown.
- [`cover_extender.end_timed_mode`](#cover_extenderend_timed_mode) ends it now.

The cover's `select.<cover>_cx_mode` shows when the countdown ends and which mode follows, in its `mode_ends_at` and `return_mode` attributes. The countdown survives a restart of Home Assistant. Going back is a mode change like any other: the lock, the exclusions and the inhibitions apply.

### Exclusions

The cover editor has two lists of entities that hold the cover back while one of them is `on`:

- **Safety exclusions**: a window or door contact (`binary_sensor`), a rain sensor. Nothing moves, **not even a priority mode**.
- **Inhibitions**: an `input_boolean` "guest in the room", "children asleep", or a template sensor such as "Wednesday morning". Cover Extender leaves the cover alone, **except for a priority request**: a mode with **Priority mode** ticked, or [`apply_mode`](#cover_extenderapply_mode) with `force: true`.

While one of them holds the cover:

- a mode change or a Cover Extender action does not move the cover: its position **waits, and is applied as soon as nothing holds it any more**. Close the window and the *Night* mode you chose meanwhile closes the cover; when the guest leaves, the morning opening that waited is applied;
- shading and solar gain skip the cover, and catch up as soon as nothing holds it any more;
- turning the lock off does not apply the memory.

A priority request that waits for a window applies as soon as the window closes, even if an inhibition is still on; a plain one keeps waiting for the inhibition too. Only the latest request waits: a new mode replaces it. If the cover got locked meanwhile, an action's position stays in memory until the unlock, as any command made while locked. A pending position does not survive a restart of Home Assistant.

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

- **Automatic shading enabled** is ticked on the cover (or its template), which creates `switch.<cover>_cx_auto_shade`;
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

It runs when **Solar gain enabled** is ticked on the cover (which creates `switch.<cover>_cx_auto_solar_gain`), that switch is on (a mode with the *Solar gain* behavior does it), and no exclusion is active. Then:

- if the temperature entity is at or above the threshold, **nothing happens** (the cover stays where it is);
- otherwise, if the sun [faces](#facades-and-orientation) the cover and the weather is in the good conditions list, the cover goes to **Position in the sun** (default 100 %);
- otherwise it goes to **Position when cold** (default 0 %).

The temperature entity, threshold and weather entity are shared by all covers (**Settings → General settings**). Without a temperature entity, the temperature check is skipped; without a weather entity, the weather is considered good. The threshold is a number, or an `input_number` so that you can change it from a dashboard. Solar gain is re-evaluated at every change of the sun, the temperature, the threshold or the weather.

### The global mode selector

`select.cx_modes` lists every mode that is not hidden, with its icon and color. **Choosing a mode on it applies that mode to every cover**, from a dashboard or an automation (`select.select_option`), following the two rules below. No automation is needed to connect it any more: if you had the one earlier versions of this README suggested, delete it.

### Who replaces whom

A grouped request (the global selector, a [schedule](#schedules), or the [`apply_mode`](#cover_extenderapply_mode) action) applies one mode to many covers at once. Two settings of each mode shape it, under **Grouped requests** in the mode editor:

- **Does not replace**: the modes it leaves alone. A cover already in one of them keeps it. A cover in a [timed mode](#timed-modes) keeps it too, and takes the requested mode when the time is up.
- **Fallback mode**, in the mode editor: applied instead, to the covers the requested mode is not linked to.

For example:

| Applying… | leaves alone covers in… |
|---|---|
| *Automatic* | *Guests*, *Away*, *Nap*, *TV*, *Air conditioning* |
| *Night* | *Away*, *Guests*, *Air conditioning* |
| *Shade* | *Guests*, *TV*, *Nap*, *Manual*, *Air conditioning* |

with *Away* falling back to *Automatic* on the covers it is not linked to. *Night* then closes the bedroom during a nap, but not the guest room; *Shade* goes on while the house is away; and choosing *Away* on the global selector puts the covers without an *Away* position in *Automatic*.

A choice made on one cover's own selector always applies, and so does `apply_mode` with `force: true`: these two settings only govern grouped requests.

---

## The admin panel

All configuration lives in the panel at `/cover-extender`. Every value is checked by the server before it is saved. The panel follows your Home Assistant theme ([dark version](https://raw.githubusercontent.com/Pulpyyyy/cover-extender/main/docs/panel-matrix-dark.png)) and each administrator reads it in their own language (English and French).

| Tab | What it edits |
|---|---|
| **Covers** | The covers: entity, facade, template, [safety exclusions and inhibitions](#exclusions), geometry, shading and solar-gain settings. Each card shows what the cover is doing right now: its mode and position, then whatever holds it back (a [timed mode](#timed-modes) with its end time, the lock with the remembered position, an exclusion or an inhibition that is on). |
| **Matrix** | Modes × covers: link modes and set every per-cover position from one grid. |
| **Modes** | Icon, color, lock, behavior, priority, fallback, [duration](#timed-modes) and what happens at its end, visibility. Drag the tiles to reorder: the order drives the mode selectors. Under **Grouped requests**: the modes it does not replace, and its fallback (see [who replaces whom](#who-replaces-whom)). |
| **Schedules** | The [morning opening and evening closing](#schedules): the curve of each over the year, and each cover's morning and evening mode. |
| **Settings** | Facades, templates, general settings, and the list of the entities the configuration produced. |

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
| `select.<cover>_cx_mode` | always | Current mode of the cover. Changing it applies the mode. |
| `switch.<cover>_cx_lock` | always | The [lock](#lock-and-memory). |
| `switch.<cover>_cx_auto_shade` | shading enabled on the cover | Turns [shading](#autonomous-shading) on or off. |
| `switch.<cover>_cx_auto_solar_gain` | solar gain enabled on the cover | Turns [solar gain](#solar-gain) on or off. |
| `binary_sensor.<cover>_cx_sun_facing` | option in General settings | The sun faces the cover. |
| `binary_sensor.<cover>_cx_auto_shade_status` | option in General settings | Shading is enabled on the cover. |
| `binary_sensor.<cover>_cx_solar_gain_status` | option in General settings | Solar gain is enabled on the cover. |

Global: `select.cx_modes`, see [the global mode selector](#the-global-mode-selector); `binary_sensor.cx_day`, `sensor.cx_morning_opening` and `sensor.cx_evening_closing` while a [schedule](#schedules) is on.

Every id contains `_cx_`: search for it to find all the entities Cover Extender created. They are attached to the cover's own device and show on its page; a cover without a device (a template cover, for example) has its entities on the **Cover Extender** device instead. Their names are fixed English (`CX lock`, `CX mode`...), the same in every language, so logs and screenshots read the same for everyone.

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

Applies `mode` to the target covers, as a grouped request: covers in a mode it leaves alone keep theirs, covers it is not linked to take its fallback mode (see [who replaces whom](#who-replaces-whom)). Returns the covers that were changed, those skipped, and why (`spared`, `not_linked`).

```yaml
action: cover_extender.apply_mode
target:
  entity_id: [cover.office, cover.living_room]
data:
  mode: Shade
response_variable: result   # optional: {"applied": [...], "skipped": [...], "reasons": {...}}
```

`force: true` makes the request a priority one: it passes the [inhibitions](#exclusions), never the safety exclusions, and re-applies the mode even on covers that are already in it. For example, to close everything when the alarm is armed, guest room included:

```yaml
action: cover_extender.apply_mode
target:
  entity_id: "{{ states.cover | selectattr('attributes.facade', 'defined') | map(attribute='entity_id') | list }}"
data:
  mode: Night
  force: true
```

#### `cover_extender.end_timed_mode`

Ends the [timed mode](#timed-modes) of the target covers now: each one goes back to its base mode (or to the mode's fixed return mode), as when the time is up.

```yaml
action: cover_extender.end_timed_mode
target:
  entity_id: cover.living_room
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
| `cover_extender_timed_mode_ended` | A timed mode ends (time up or `end_timed_mode`) | `entity_id`, `mode`, `return_mode` |

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
                  │ Timed mode: start, extend or    │
                  │ end the countdown               │
                  └─────────────────────────────────┘
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
             │ A safety exclusion on, or an       │
             │ inhibition on and the request is   │
             │ not a priority one ?               │
             └────────────────────────────────────┘
                   │ NO                       │ YES
                   ▼                          ▼
        ┌────────────────────────┐   ┌───────────────────────────┐
        │ Send cover command     │   │ Do NOT move the cover     │
        │ (throttled queue)      │   │ Apply it once nothing     │
        └────────────────────────┘   │ holds the cover any more  │
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
 │ Nothing holds the cover back ?      │         │
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

**My cover does not move.** The cover's card in the **Covers** tab says why. It is one of these: the cover is **locked** (`switch.<cover>_cx_lock` is on, the requested position is in the `memory` attribute), a **safety exclusion** or an **inhibition** is on, or the mode has **no position** for this cover (None, or the mode is not linked to it in the matrix). For shading, also check the change threshold and the time-out.

**I moved my cover by hand and it went back on its own.** Shading or solar gain is on. Shading waits for the time-out after any movement, then resumes. To keep your position, switch to a mode without a behavior, or turn `switch.<cover>_cx_auto_shade` off.

**My cover changed mode on its own.** A [timed mode](#timed-modes) ended (the cover went back to its base mode, or to the mode's fixed return), or a [schedule](#schedules) applied its morning or evening mode. The `cover_extender_timed_mode_ended` and `cover_extender_mode_changed` events, and the logbook of `select.<cover>_cx_mode`, tell which.

**A cover did not follow the global selector (or an `apply_mode` on several covers).** It was in a mode the requested one leaves alone, or the mode is not linked to it and has no fallback mode: see [who replaces whom](#who-replaces-whom). `apply_mode` returns the reason per cover in `reasons` (`spared`, `not_linked`).

**I cannot find the panel.** Open `http://<your-ha>:8123/cover-extender` directly. The panel needs an administrator account. If the sidebar entry is missing, it may be hidden: open your **Profile** and change the sidebar items there.

**`switch.<cover>_cx_auto_shade` does not exist.** Tick **Automatic shading enabled** in the cover's Shading section (or in its template). Same for solar gain.

**The cover closes too much / not enough in shading.** Increase **Distance from the cover** to let more sun in, raise **Minimum position** to keep some light. After each change, [`compute_shade_position`](#cover_extendercompute_shade_position) (in **Developer tools → Actions**) shows the new position without moving the cover.

**How do I get debug logs?** Add this to `configuration.yaml` and restart, or use **Enable debug logging** on the integration page:

```yaml
logger:
  logs:
    custom_components.cover_extender: debug
```

Each decision (lock, exclusion, inhibition, priority, threshold, time-out, timed mode, schedule) is logged with its reason.

---

## Uninstall

1. **Settings → Devices & services → Cover Extender → ⋮ → Delete.** The helper entities, the added attributes and the stored memory are removed. Your covers are untouched.
2. Remove the integration from HACS (or delete `custom_components/cover_extender/`), then restart Home Assistant.

---

## Support and contributing

- Bugs and feature requests: [GitHub issues](https://github.com/Pulpyyyy/cover-extender/issues). Please include your Home Assistant and Cover Extender versions and the debug logs.
- What changed in each version: [CHANGELOG](https://github.com/Pulpyyyy/cover-extender/blob/main/CHANGELOG.md).
- License: [LICENSE](https://github.com/Pulpyyyy/cover-extender/blob/main/LICENSE).
