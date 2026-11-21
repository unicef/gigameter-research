# 0003. Versioning and freeze

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

A code tag, the package version, and the published docs version can move separately. A wiring fix can ship without changing the method.

## Decision

Tag releases `git tag vX.Y.Z`. Publish the docs with `mike` as a minor version `vX.Y`. Bump `mike` only at a freeze. Run `scripts/replay_versions.py` before every freeze, and keep replay outputs outside the repository. Record every method change in the Research Log.

A patch release does not get its own `mike` version. Docs stay on the minor, as in `v0.3` for the `v0.3.x` tags.

The docs version is the Spatial Intelligence & Geofencing methodology version and appears as plain `vX.Y` in the version picker. The Outage and Routing pages are marked as unversioned drafts.

Keep `pyproject.toml` `version` equal to the release tag.

## Open questions

Per-track sites and track-prefixed tags are proposed in [ADR 0016](0016-per-track-documentation-sites.md). Existing tags `v0.3.0`, `v0.3.1`, and `v0.3.2` stay as they are. `pyproject.toml` was left at `0.3.0.dev0` through `v0.3.0` and `v0.3.1` and set to `0.3.2` with tag `v0.3.2`.

## Evidence

- `README.md`, Versioning: geofencing docs are published with `mike deploy --deploy-prefix geofencing --update-aliases --title "v0.3" v0.3 latest`.
- [Research Log](/gigameter-research/geofencing/latest/blueprint/research-log/): status is frozen after replay validation. The "Operational-hours wiring" entry chooses no new version label.
- `scripts/replay_versions.py`: outputs go to `--out`, default `/tmp/gigameter-replay`.
- `pyproject.toml`: `version = "0.3.2"`.
