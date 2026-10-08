# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - Unreleased

### Changed (breaking)
- **Entity ids now say where they come from: `<cover>_cx_<function>`.** Reported on the HACF forum: on an install with many entities, nothing told the helpers apart from everything else. The cover comes first, so a helper sorts next to its cover, then `cx`:

  | 3.x | 4.0 |
  |---|---|
  | `select.mode_<cover>` | `select.<cover>_cx_mode` |
  | `switch.<cover>_lock` | `switch.<cover>_cx_lock` |
  | `switch.<cover>_auto_shade` | `switch.<cover>_cx_auto_shade` |
  | `switch.<cover>_auto_solar_gain` | `switch.<cover>_cx_auto_solar_gain` |
  | `binary_sensor.<cover>_sun_facing` | `binary_sensor.<cover>_cx_sun_facing` |
  | `binary_sensor.<cover>_auto_shade` | `binary_sensor.<cover>_cx_auto_shade_status` |
  | `binary_sensor.<cover>_solar_gain` | `binary_sensor.<cover>_cx_solar_gain_status` |
  | `select.cover_extender_modes` | `select.cx_modes` |

  Existing entities are renamed once, at the first start of 4.0 (config entry 2.1 → 2.2). Only ids still in their 3.x shape are renamed, keeping their cover part as it is; an id you had rewritten is left alone, and a rename whose target is already taken is skipped with a warning in the log. Locks, current modes and shading switches keep their state across the rename (the restore cache is re-keyed, since Home Assistant keys it by entity id). History follows the rename too; automations, scripts and dashboards do not: a **Repairs** issue lists every old → new pair. Going back to 3.x still loads (minor version bump only); the entities then keep their 4.0 ids.

### Added
- **Roof windows and skylights: a facade has a slope.** Every window was taken as upright, so a roof window was shaded as if it were in a wall: a north roof never saw the summer sun that reaches it from behind. A facade now has a **slope**, the glass's angle with the horizontal, set in its editor as *Wall* (90°, the default), *Roof* (10° to 89°) or *Flat* (0°). Whether the sun reaches the glass follows the angle of incidence: a roof window also sees the sky behind it once the sun is higher than the slope, a flat skylight sees the whole sky. A roof window's angles go up to 180° on each side (then they only mask a dormer or a neighbour), and its range of sun heights runs over the zenith down to the roof, one cone on the profile sketch; shading leaves open a length of glass `distance × sin(elevation) / cos(incidence)` along the slope, measured at the level of the glass's lower edge. A flat skylight takes a new *position in direct sun* instead of the geometry. The cover editor draws each shape (cross-section along the slope, top view with the sky behind the roof, profile) and words its fields to match. On a wall every formula gives back the vertical case exactly. A **template has a window type** too (*Wall*, *Roof* or *Flat*): its fields, sketches and limits follow it, and a cover only takes a template of its facade's type (the server refuses a mismatch, whichever of facade, template or cover the save changes). At the first start of this version, a template whose covers all sit on roof facades (or all on flat ones) takes that type; the others are a wall's.
- **The global selector applies the mode, and who replaces whom.** Choosing a mode on `select.cx_modes` now applies it to every cover; the automation the README suggested to connect it is no longer needed. Grouped requests (the global selector, schedules, `apply_mode`) follow two new mode settings, set in the mode editor: the modes it **leaves alone** (a cover in a timed mode keeps it and takes the requested mode at its end), and a **fallback mode** applied to the covers the requested mode is not linked to. A choice made on one cover's own selector, and `apply_mode` with `force: true`, always apply. `apply_mode` now returns the reason per skipped cover (`reasons`). Replaces scripts that walked the covers to apply a global mode with exceptions.
- **Schedules: a morning opening and an evening closing that follow the sun.** New Schedules tab: each time follows sunrise or sunset over the year between a max and a min time, with optional spring / autumn crossings that land exactly on the sun event, a floor and a ceiling in legal time, or a fixed time; edited as fields, as handles dragged on a chart of the year, or by double-clicking a handle to type its value. At each, every cover applies its own morning / evening action: a mode, as a plain mode change (lock, exclusions, inhibitions, timed modes apply), or a fixed position, which leaves the mode alone and either respects the lock (a locked cover keeps it in memory for when it leaves the locked mode) or forces it (the cover moves even locked and passes the inhibitions, its memory takes the position too; an open window still holds it back). A schedule missed while Home Assistant was down is applied at startup (the latest of the day, never on the first start). New entities on the Cover Extender device: `binary_sensor.cx_day` (with `opening`, `closing`, `next_change`, `cause`), `sensor.cx_morning_opening`, `sensor.cx_evening_closing`. The curve is computed in Python; the panel only draws it.
- **Timed modes.** A mode can last a while (1 minute to 24 hours), then hand the cover back. It is a parenthesis over the cover's base mode, the last mode without a duration the cover was put in: when the time is up, the cover returns to that base mode, or to a fixed mode chosen in the mode editor (*Manual: 1 h, then Day*), which can only be a mode without a duration, so no chain of returns can loop. Another timed mode chosen meanwhile replaces the parenthesis and keeps the base mode; a mode without a duration closes it at once; the running timed mode chosen again extends it. New action `cover_extender.end_timed_mode`, new event `cover_extender_timed_mode_ended`, and `mode_ends_at` / `return_mode` attributes on the cover's mode selector. The countdown survives a restart.
- **Inhibitions, next to the safety exclusions.** A cover now has two lists of entities that hold it back. **Safety exclusions** (the existing exclusion entities, unchanged: an open window) block every move, priority included. **Inhibitions** (new: a guest in the room, children asleep, a "Wednesday morning" template sensor) block every move Cover Extender makes, mode changes, shading, solar gain and actions alike, except a priority request. What was asked meanwhile is applied once nothing holds the cover; a priority request waiting for a window goes as soon as the window closes, even with a guest still there.
- **`force` on `set_cover_position`.** `force: true` moves locked covers too, writes the position to their memory so that leaving the locked mode does not undo it, and passes the inhibitions, never the safety exclusions. Same engine as a forced scheduled position.
- **Priority modes, and `force` on `apply_mode`.** A mode can be flagged **Priority mode** in the panel: it passes the inhibitions, never the safety exclusions (an *Alarm* mode that closes every cover, guest room included). `apply_mode` takes `force: true` for the same effect on one call, which also re-applies the mode on covers already in it. Priority modes carry a chip on their row and a word in the matrix header; the mode selectors expose a `priority` flag per mode.
- **Panel: what each cover is doing.** Each cover card shows its current mode and position, then whatever holds it back: a running timed mode (*back to Day at 21:30*), the lock with the remembered position, a safety exclusion or an inhibition that is on. A cover that follows a schedule also shows its morning and evening actions with today's times, the next one marked (*tomorrow 08:06* after the closing), and what its state now changes at that next one: *Locked: 0 % goes to memory*, an open window it will wait for, a mode it does not replace, a forced position the shading can move again. A click on the row opens the Schedules tab; the cover's editor shows the same row. Live, from Home Assistant's states.
- **Panel: the generated entities are listed**, not only counted, under Settings.
- **The entities show under their cover.** Each helper is attached to its cover's device, so it appears on that device's page and under the integration, instead of nowhere. It is linked with `Entity.device_entry`, which does not add Cover Extender to a device another integration owns. A cover without a device has its helpers on the Cover Extender hub device, named after the cover. `select.cx_modes` lives on the hub device too.

### Changed
- **Panel: reorganised to read top to bottom.** Six tabs instead of five: the four everyday ones in the order of the work (*Covers*, *Modes*, *Matrix*, *Schedules*), then, past a rule, the two set once: **House** (facades and templates, moved out of Settings) and **Settings** (solar gain, commands, extra entities, the generated entities last). The panel opens on *Covers*. A save bar only shows with something to save, stuck to the bottom of the screen, and the tab holding the changes gets a dot. *Covers*: cards grouped by facade, the position drawn as in the matrix, the schedules on one line, only the features that are on. *Modes*: a list in the selector's order, each row saying how the mode places the covers. *Matrix*: the hint and the legend on one line, the mode's options in words under its name (a header opens the mode), one line per cover, empty cells a quiet dot, an override outlined in amber, a cell of a plain mode with no position saying *none* rather than *auto*, and a per-cover view on phones. The cover editor gains its row of the matrix (edited with the same popover, saved with the cover), a bar of shortcuts to its sections (amber dot where it overrides its template), one sentence for where its values come from, and inherited values that look at rest. The mode editor is one column, its rules for grouped requests two sentences to complete. *Schedules* opens on a card per schedule (switch, today's time, what it does to the covers), then the per-cover table, then the curve; "floor" and "ceiling" become *not before* and *not after*, and the figures under the curve go from five to three. Solar gain reads as its rule, the chosen weather conditions first. A template names the facades of its type, and a cover only lists the templates of its facade's type. On a phone, the schedule table's lists no longer grow 200 px tall.
- **Panel: sketches that fill their box, and a few readability fixes.** The cross-section, the top view and the profile size themselves to their box on every screen and lay out from the values drawn (a roof whose angles stay in front no longer leaves half the top view for the sky behind it; a short roof window is no longer drawn small in a corner), and their labels get a halo so a line crossing them no longer hides them. The facade arrow on the cover cards, the facade list and next to the facade field points where the windows look, north up, instead of a red arrow towards north that read as an error; the north arrow stays in the top view, beside its "N". The slope card keeps its controls next to its sketch, and explains what *Roof* and *Flat* change. "1 cover" / "2 covers" instead of "cover(s)". On a phone the tabs share a full row. The top view calls the side behind a wall "room", like the cross-section and the slope sketch.
- **Maximum sun height: 180° means no limit.** Heights now read over the zenith, down the far side of a roof, so the stored default of 90° would stop a roof window's shading at the zenith. At the first start of this version (config entry 2.2 → 2.3), every maximum height of 90° in templates and covers becomes 180°; on a wall the two behave the same. Values under 90° were chosen and are kept.
- **Shading uses the cover's left / right angles; the angular aperture is gone.** Two settings answered the same question, "is the sun in front of the window?": the left / right angles for solar gain and the "sun facing" sensor, a symmetric ± aperture for shading. They could disagree (shading closing a cover the sensor said the sun did not face), and an aperture above 90° closed the cover for a sun behind the wall. Shading now uses the same left / right sector, and a sun behind the wall never counts, whatever the angles. The aperture field leaves the panel; a value stored by an earlier version is ignored, and dropped from a cover at its next save. With the defaults (85° each side, aperture 90°) shading only loses the grazing band between 85° and 90°.
- **Panel: the editors are reorganised around the questions they answer.** Same settings, nothing removed. Every editor opens on one identity strip (no more title repeating the name field), then cards in two columns on a wide screen, one on a phone, each with a one-line hint and the detail in an (i) tooltip.
  - **Mode**: name, icon and colour on one line with a live preview of the selector chip; the colour is a colour wheel plus its hex code, instead of the full-width colour bar. Behaviour as three buttons (*Fixed*, *Shading*, *Solar gain*); *While this mode is on* (lock, limited duration as "For 60 min, then…"); *Applied to several covers* (the modes it leaves alone, ticked and counted, and what to do with the covers the mode is not linked to); priority and hiding under *Advanced*, open by itself when one of them is on.
  - **Cover**: entity, facade and template on one line with the cover's current state; safety exclusions and inhibitions side by side under *What holds the cover back*, as chips showing each entity's state; the behaviour fields as four cards, every value a typed box plus a short slider and a hint, a side-view sketch of the window for the geometry and a sketch of the angles for the detection, the activation switch in each card's header, minimum and maximum sun elevation as one range with two thumbs, and, under a template, each value says where it comes from: inherited in a dashed grey box with a link, the cover's own in amber with the template's value (also marked on the slider) and a "back to the template" button; each card counts both, the head shows a legend and an *Overrides only* filter. A link opens the cover's template.
  - **Template**: the same cards, and the covers that use it.
  - **Facade**: the azimuth on a compass, dragged or typed, with eight direction buttons; the covers on that facade.
  - **Settings**: the house (facades, templates, generated entities) on the left as compact lists; the general settings on the right, grouped as solar gain (the threshold typed as a value or taken from an entity, the current temperature against it, and the fine-weather states as chips), sending commands, and extra entities per cover; their save bar shows only once something changed.
  - **Schedules**: one line on top, the detail in a tooltip; each schedule shows its time today and whether it is on, the reference ("follows the sunset, today 19:08") and an *On* switch in the header; the six settings in three groups (curve over the year, bounds in legal time, crossings folded under *Fine-tune*), bounds and crossings switched like the rest; the chart unchanged. The per-cover table is grouped by facade, with an *All covers* row and the covers that differ from the others highlighted, each list edged with its mode's colour; the save bar shows only once something changed.
  - **One save bar everywhere**: every editor, the general settings and the schedules end on the same bar, stuck to the bottom of the screen (Delete on the left when there is one, then what is pending, Cancel and Save). Cancel and Save stay greyed out until something changes and go back to grey when the change is undone.
  - On a phone the tab bar scrolls instead of widening the page, and the schedule table shrinks to fit.

### Fixed
- Panel: the end time of a timed mode on the cover cards is shown in Home Assistant's time zone, like the schedules; it followed the browser's, so a phone in another zone showed another hour.
- Panel: the mode chip on the cover cards wears the mode's colour (icon, tint and edge), as on the mode tiles and in the matrix; it was a faint tint only.
- Panel: the template field of the cover editor is labelled "Template" ("Gabarit"), capitalized like the other fields.
- **Actions keep working with Home Assistant 2026.10** (also released alone as 3.1.3). The targeted actions passed `hass` to `async_extract_entity_ids`, which Home Assistant removes in Core 2026.10.
- **The entities have a name.** They declared a translation key with no translation behind it, so Home Assistant showed their raw entity id. Names are now fixed English (`CX mode`, `CX lock`, `CX auto shade`, `CX auto solar gain`, `CX sun facing`, `CX auto shade status`, `CX solar gain status`, `Modes`), never translated, so logs, screenshots and forum reports read the same in every language. The leading `CX` keeps Home Assistant's "rename the entity ids with the device" suggestion on the cx scheme.

## [3.1.3] - 2026-10-06

### Fixed
- **Actions keep working with Home Assistant 2026.10.** Every action that takes a target (`apply_mode`, `set_cover_position`, `open_cover`, `close_cover`, `apply_memory`) passed `hass` to `async_extract_entity_ids`, an argument Home Assistant deprecated and removes in Core 2026.10; it also logged a warning at each call. The call now uses the current signature, available since 2026.1, the minimum supported version.

## [3.1.2] - 2026-09-24

### Added
- **A position blocked by an exclusion is applied when the exclusion clears.** Choose *Night* with the window open, close the window: the cover closes. The pending position is tracked apart from the memory (which may still hold a position from an older locked period and must not come back), only the latest request waits (a new mode replaces it), and an action's position on a cover locked meanwhile stays in memory until the unlock. A locked mode chosen while excluded no longer overwrites the memory, so the position saved on entering the mode is still restored when leaving it. Shading and solar gain also catch up immediately instead of waiting for the next sun update. Position changes of a mode's entity made while excluded now wait too, instead of being dropped.

### Fixed
- **Exclusion entities now block every move Cover Extender makes.** They were only checked on mode changes, on unlock and for entity-driven positions: autonomous shading (periodic and on entering a shading mode), solar gain and the `set_cover_position` / `open_cover` / `close_cover` actions moved the cover even with the window open. Shading and solar gain now skip an excluded cover and resume at the next sun, temperature or weather update once the exclusion clears; the actions store the position in memory, as a mode change already did.
- Panel: the lock hint no longer claims to block every manual command (a remote or a native `cover.*` call still moves the cover; only commands made through Cover Extender are memorized), and the "Automatic shading" / "Solar gain" display options are labelled as the binary sensors they create, not switches.

### Documentation
- README rewritten for new users: HACS installation, a step-by-step quick start, key concepts (lock and memory, exclusions, orientation, shading settings explained), the global mode selector and the automation that drives it, action parameters, FAQ and troubleshooting, uninstall.
- French guide (`README.fr.md`) and GitHub issue templates.

## [3.1.1] - 2026-09-22

### Fixed
- **No more `Referenced entities switch.<cover>_auto_shade are missing` warnings at every mode change.** `_apply_mode_core` called `switch.turn_off` on the `auto_shade` and `auto_solar_gain` helpers of every cover, including those that do not enable shade or solar gain and therefore have no such switch (`resolve_helper_entity` falls back to a conventional entity_id when the helper is not registered). Each helper is now checked against the state machine first, as the lock path already did: a missing helper that should stay off is skipped silently, and one that should be turned on logs an explicit warning naming the cover and the mode. The log stops being flooded, so a genuine switch failure stays visible.

## [3.1.0] - 2026-08-18

### Added
- **Per-cover override of automatic modes.** In the matrix, a mode with an `auto_shade` or `solar_gain` behavior now offers the same three choices as any other mode: **Auto** (computed, the default), **Fixed** or **Entity**. Choosing Fixed or Entity overrides the computation for that cover only - the auto switches stay off for it, the stored position is applied, and lock/memory follow the mode's own lock flag instead of being forced. Every other cover linked to the mode keeps the computed position. Overridden cells carry a tooltip in the matrix.
- Screenshot harness (`docs/screenshot-harness.html`): renders the real panel JS against a faked `hass` and websocket payload, for reproducible README screenshots (light/dark, every tab, popover states) via headless Chromium/Edge.
- The test suite now covers the panel's server-side validation (`websocket_api.py`, the sole writer of the configuration since 3.0.0): item validators, template flatten/pack round trip, per-cover mode configs (overrides on behavior modes included), the picture host-relative guard, template-value stripping, the deletion guard and the rename cascade. `tests/test_schemas.py` was rewritten for the options-based builder that replaced the subentry one.

## [3.0.0] - 2026-08-16

### Breaking
- **The config flow wizards are gone; configuration now lives in an embedded admin panel** served at `/cover-extender` (sidebar entry, per-user visibility; also linked from the integration page and the hub device's configuration URL). The config flow only creates the entry and stops there.
- **Storage moved from config subentries to `entry.options["config"]`** - config entry version 1 → 2, migrated automatically at startup. The migration is one-way: a downgrade to 2.x is refused rather than risking corruption.

### Added
- Admin panel with four tabs: **Covers**, **Matrix** (modes × covers - the screen a config flow cannot draw), **Modes** (drag to reorder; the order drives the mode selectors), **Settings** (facades, templates, global settings, and a read-only count of the entities the configuration produced).
- Matrix cell popover: link/unlink a mode, set the per-cover position (fixed slider, entity, none), apply to the whole facade in one tick.
- Two admin-only WebSocket commands (`cover_extender/config/get` / `config/save`). All validation stays server-side: the behavior field table (defaults, bounds, units) is sent to the panel, deleting a facade/template/mode still referenced by covers is refused, renames cascade to the covers referencing them.
- The panel carries its own EN/FR dictionary keyed on the reader's language (`hass.locale`), with key-by-key English fallback.

## [2.4.0] - 2026-07-26

### Added
- **Shared external-attrs contract** — extra attributes (modes, auto_shade, sun_facing…) meant for a "reader" cover (a fork exposing the shared `hass.data['cover_external_attrs']` contract, e.g. ESPSomfy-RTS Enhanced v3.4.0) are now deposited in the contract instead of being written back onto the cover state. This ends the attribute ping-pong that multiplied `state_changed` events and froze the display while several covers were moving. Readers are detected dynamically; every other cover (velux mqtt, esphome, older firmware) keeps the `async_set` fallback, so the integration works whether the target component is present or not.
- **Integration brand images** shipped locally in `custom_components/cover_extender/brand/` (`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`). Since HA 2026.3 these take priority over the brands CDN, so the integration shows its own icon without being listed in the Home Assistant brands repository.

### Fixed
- Covers deleted and re-created (e.g. a platform swap) migrate their helper entities instead of creating duplicate `*_2` helpers: the stored registry id is now part of the legacy keys checked at startup.

### Removed
- Compiled `__pycache__` bytecode that had been committed by mistake, and the duplicate `icon.png` / `logo.png` that sat at the integration root (an unused location, superseded by `brand/`).

## [2.3.0] - 2026-07-04

### Added
- **Per-cover mode positions are now editable** (previously: unlink then relink). Two entry points: from a cover, the "Link modes" action re-asks the position of every selected non-automation mode; from a mode, a new "Per-cover positions" action edits the mode's position on every linked cover in a single page. The current value is always visible (in the cover's field label, or in the screen description), an untouched field keeps it, and fixed positions pre-fill the slider (the HA frontend cannot pre-open a `choose` selector on entity/none values).
- Config flow validation with inline errors: duplicate or empty facade/mode/template names refused, already-configured cover refused, facade required, min/max coherence checks on heights and sun elevations. Adding a cover aborts with an explicit message when no facade exists yet.
- Deleting a facade, template or mode still referenced by covers is blocked, with the list of covers using it.
- Manage lists show what matters at a glance: usage counts everywhere, facade azimuth, template dimensions (height range + obstacle distance), mode markers (lock / behavior / hidden), and per-cover facade + template + linked-mode count.
- The test suite now validates `strings.json` and `fr.json` against the real hassfest translations schema (vendored) and asserts key parity between the two files.

### Changed
- Facade and template dropdowns are sorted, show the azimuth, and display a translated placeholder instead of an empty option when nothing exists yet; the mode multiselect carries lock/behavior markers.

### Fixed
- hassfest validation passes: `__add__` selector keys renamed to `add`, subentry translation key `entry_title` renamed to the official `entry_type`, JSON-literal braces removed from the `apply_mode` service description, required empty `config.step` key added.
- `manifest.json`: added the required `issue_tracker` URL and fixed the `documentation` URL.

## [2.2.0] - 2026-07-04

### Changed
- **Covers are now tracked by their entity registry id** (immutable) instead of their entity_id: renaming a cover in HA no longer breaks the configuration, the helper entities, the memory or the automations. The stored entity_id is kept in sync automatically (live via a registry listener, and at startup for renames done while HA was stopped).
- Helper entities' unique_ids migrate automatically from the name-based scheme to the registry-id scheme at first startup — entity_ids, names, areas and history are preserved. Covers without a registry entry (e.g. YAML template covers without unique_id) keep the legacy name-based behaviour.
- Stored memory positions are re-keyed from entity_id to registry id at first load.
- Renaming a helper entity (mode select, lock/auto switches) is now picked up immediately instead of at the next reload.

### Notes
- The helper entities keep their original entity_id after a cover rename (HA standard behaviour) — rename them manually if you want matching names; this breaks nothing.
- Automations filtering `cover_extender_*` events on `entity_id` must follow the new cover id after a rename, like for any HA entity.

## [2.1.0] - 2026-07-04

### Fixed
- `compute_shade_sync` no longer looks up a hardcoded "Ombre" mode (crashed when a mode with that name used an entity-driven position); the default shade position now always comes from `default_position`.
- Guard against covers reporting `current_position: None` (position unknown / moving) — no more `TypeError` in the shade computation.
- The shade `time_out` throttle now works: it is driven by per-cover last-move timestamps (commands sent by the integration AND position changes observed from any source: remote controls, HA UI, other automations) instead of the unreliable state `last_changed`.
- Memory save/restore follows the *effective* lock: modes with an `auto_shade` / `solar_gain` behavior force the lock on, so entering/leaving a `lock: false` behavior mode no longer loses the cover's previous position.
- Services declared with `target:` (`set_cover_position`, `open_cover`, `close_cover`, `apply_memory`, `apply_mode`) now accept area, device and label targets.
- No more worker restart or deferred listener setup after the entry is unloaded (leak on unload before HA finished starting).
- Injected attributes (`facade`, `modes`, `memory`, …) are stripped from covers removed from the configuration instead of lingering until restart.
- `default_height_m` accounts for `min_height` in the shade geometry.
- A failed switch call during a mode change no longer aborts the mode mid-way (position is still applied).
- `_handle_mode_entity_change` respects the exclusion entities, like the other position paths.

### Changed
- Helper entities (mode select, lock / auto-shade / auto-solar-gain switches) are resolved through the entity registry — renaming them in the UI no longer breaks the integration.
- The coordinator lives on `entry.runtime_data`; `manifest.json` declares `integration_type: helper` and `single_config_entry: true`; minimum HA version (2026.1.0) is declared in `hacs.json`.
- Memory positions are persisted with a debounced storage save (flushed on HA shutdown).

## [2.0.0] - 2026-06-24

### Breaking
- **YAML configuration removed** — configuration is UI-only (config subentries).

### Added
- Explicit per-cover mode position choice: Fixed % / Entity-driven / None.
- Mode `behavior` field (`auto_shade` / `solar_gain`) with automatic lock and switch handling.
- Config flow ergonomics: collapsible sections, help texts, `choose` selector, cascade rename of facades/modes/templates across covers, "link modes" shortcut.
- Shade position applied immediately on mode entry.

## [1.1.0] - 2026-04-??

### Added
- **Full UI configuration** via HA config subentries (requires HA 2024.11+). Manages facades, modes, cover profiles and global settings entirely from the HA interface.
- **Cover templates** (`cover_template` subentry type): reusable angle + shade/solar-gain settings shared across multiple covers. Template changes propagate automatically to all covers referencing them.
- `temperature_threshold` in solar-gain global config now accepts an `input_number` entity ID in addition to a static float value. The threshold is resolved at runtime from the entity state.
- Minimum HA version declared in `manifest.json`: `2024.11.0`.

## [1.0.0] - 2026-04-11

### Added
- Initial release
- Config flow UI setup with YAML profile validation
- Mode selection entity (`select.mode_<cover>`) per cover
- Global mode selector (`select.cover_extender_modes`)
- Lock switch (`switch.<cover>_lock`) to block automations
- Auto-shade switch (`switch.<cover>_auto_shade`) for solar shading
- Sun-facing binary sensor (`binary_sensor.<cover>_sun_facing`)
- Auto-shade enabled binary sensor (`binary_sensor.<cover>_auto_shade`)
- Solar shading calculation based on facade azimuth and sun position
- Automation memory system to restore positions after manual control
- Command queue with 150ms throttling to avoid cover overload
- Hot reload service (`cover_extender.reload`) without HA restart
- Services: `apply_mode`, `set_cover_position`, `open_cover`, `close_cover`, `apply_memory`, `compute_shade_position`, `get_mode_position`
- Multi-language support: English and French
- State restoration on HA restart
