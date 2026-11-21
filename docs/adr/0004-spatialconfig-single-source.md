# 0004. SpatialConfig is the single source of numbers

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

Methodology numbers were easy to copy into SQL, modules, and prose, and easy to treat as permanent once copied.

## Decision

Keep methodology numbers only in `SpatialConfig` and on the Parameters page. Do not hard-code them. Do not treat the current values as permanent. Stamp outputs with `methodology_version` and `config_hash`.

Read `operational_hours` from that same config. It was the setting that broke this rule; v0.3.1 wires it back. See [ADR 0011](0011-operational-hours.md).

## Open questions

The policy for versioning per-country overrides is not decided. `workdays` is one config value today, not resolved per country.

## Evidence

- `src/spatial_intelligence/config.py`: `methodology_version` is `"0.3"`; `config_hash` and `provenance` stamp outputs; `with_overrides` returns a validated copy.
- [Parameters](../blueprint/parameters.md): the same settings, with current value, status, and the version that set them.
- `tests/test_spatial_foundations.py`: `test_operational_hour_window_is_not_hard_coded_outside_config`.
- [Research Log](../blueprint/research-log.md), "Operational-hours wiring". Tag `v0.3.1`.
- [Blueprint](../blueprint/technical_blueprint.md), Known Limitations: "Fixed workdays".
