# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
