# 0008. Schools only while on 0.x

- Status: Accepted
- Date: 2026-11-18
- Deciders: Utku Can Ozturk

## Context

The GigaMeter app monitors schools, health facilities, and camps. This research line joins telemetry on a school id.

## Decision

While the project is on 0.x, cover schools only. Join on `giga_id_school`, which the loader canonicalises to `school_id_giga`. Revisit this before adding a health facility or a camp. Those entities break the assumption that the platform entity id is the school id.

## Evidence

- `src/utils/data_loader.py`: `TELEMETRY_COLUMN_ALIASES` maps `giga_id_school` to `school_id_giga`; `REQUIRED_TELEMETRY_COLUMNS` requires `school_id_giga`.
- `sql/fetch_spatial_confidence_ledger.sql` reads `school.giga_id_school`.
- `README.md` describes the app's three entity types. The implemented spatial questions in this repo run on the school id.
