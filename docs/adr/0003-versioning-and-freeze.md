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

When another track reaches its first release, one version picker no longer fits. Planned direction, to be decided in a new ADR then: an unversioned landing page with shared pages, one versioned site per track under its own path (`mike deploy --deploy-prefix`), and track-prefixed tags such as `geofencing-vX.Y.Z`, with `pyproject.toml` as the package version. It was left at `0.3.0.dev0` through `v0.3.0` and `v0.3.1` and set to `0.3.2` with tag `v0.3.2`.

## Evidence

- `README.md`, Versioning: tags are `vX.Y.Z`; docs are published per minor version, for example `mike deploy --push --update-aliases v0.3 latest`.
- [Research Log](../blueprint/research-log.md): status is frozen after replay validation. The "Operational-hours wiring" entry chooses no new version label.
- `scripts/replay_versions.py`: outputs go to `--out`, default `/tmp/gigameter-replay`.
- `pyproject.toml`: `version = "0.3.2"`.
