# 0002. MkDocs is the source of truth

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

The methodology is written up in more than one place. Notebooks, chats, and dashboards drift from the write-up that was actually frozen.

## Decision

Treat the versioned MkDocs site as the source of truth for methodology. Other tools hold notes only.

## Evidence

- `README.md` says the published documentation is the source of truth for how every result is computed.
- `docs-site/geofencing/mkdocs.yml` builds the geofencing site and selects versions with `mike`.
