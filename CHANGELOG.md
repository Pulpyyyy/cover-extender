# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
