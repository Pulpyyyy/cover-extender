# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-01-01

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
