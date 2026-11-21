# 0016. Per-track documentation sites and versions

- Status: Proposed
- Date: 2026-11-21
- Deciders: Utku Can Ozturk

## Context

One `mike` version covers the whole site. Geofencing is at v0.3. Outage and routing are unversioned drafts. A second released track cannot have its own version while sharing that picker.

## Decision

Publish an unversioned landing site at the root. It carries the hero, the track cards, Decisions, and data handling.

Give each track its own MkDocs config under `docs-site/`. Shared theme, palette, and markdown extensions live in `docs-site/base.yml`. Path-based settings stay in the track config, because `INHERIT` does not rewrite paths.

Version geofencing with `mike` and `--deploy-prefix geofencing`. `versions.json` lives at `geofencing/versions.json`. The published minors are v0.2 and v0.3, with `latest` as the alias of v0.3. The picker title is plain `vX.Y`. Every `mike` command includes `--deploy-prefix`. There must never be a `versions.json` at the site root: an unversioned track requests that file, and a root file would show another track's versions.

Leave outage and routing as unversioned plain builds until each reaches v0.1. Their configs already set `extra.version.provider: mike` and a deploy prefix, so a later `mike deploy --deploy-prefix outage` does not share geofencing's version list.

From the next release onward, tag tracks `geofencing-vX.Y.Z`, `outage-vX.Y.Z`, and `routing-vX.Y.Z`. Leave the existing tags `v0.3.0`, `v0.3.1`, and `v0.3.2` as they are. Do not retag them. Keep `pyproject.toml` `version` as the package version.

Keep links inside one site relative, so they stay on that version. Point links that cross sites at root-absolute paths such as `/gigameter-research/adr/...` and `/gigameter-research/geofencing/latest/...`.

Redirect the old `/v0.2/`, `/v0.3/`, and `/latest/` URLs with `scripts/redirect_legacy_docs.py`. Geofencing pages go to `/geofencing/<version>/...`. Decision pages go to `/adr/...`. Outage and routing pages go to their unversioned sites.

Publish from a worktree of `gh-pages`. `scripts/docs.sh migrate-gh-pages` is the one-time move. `scripts/docs.sh publish` updates one site at a time. Do not use `mkdocs gh-deploy`; it replaces the branch and would wipe the geofencing tree `mike` deployed. The scripts commit locally and print `git push origin gh-pages` instead of pushing.

## Consequences

Search is per site. There is no cross-site search.

The version picker stays in the header. Material appends it to `.md-header__topic` from JavaScript. Moving it into the left nav is not a small partial override, so it is not done here.

A plain `mkdocs build` of a versioned track does not fill the picker. Publish geofencing with `mike`. `mike set-default` runs under the geofencing prefix, so the site root stays the landing page.

The copied v0.2 HTML is the already published build. It is not rebuilt from current sources.

`docs/api` and `docs/adr` remain symlinks to the geofencing API pages and the landing decisions, so the API doc test and the agent rules still resolve.

## Alternatives considered

Keeping one site and one picker until a second track releases. Rejected because the landing page, the shared decisions, and the track versions would stay tied together.

Rebuilding v0.2 from the current sources and labeling it v0.2. Rejected because those pages would no longer be the frozen build.

## Evidence

- `docs-site/base.yml` and `docs-site/{landing,geofencing,outage,routing}/mkdocs.yml`.
- `README.md`, Versioning: `mike deploy -f docs-site/geofencing/mkdocs.yml --deploy-prefix geofencing --update-aliases --title "v0.3" v0.3 latest`.
- [ADR 0003](0003-versioning-and-freeze.md): the open question points here. Tags `v0.3.0`, `v0.3.1`, and `v0.3.2` are unchanged.
- `scripts/docs.sh`: `migrate-gh-pages` and `publish` commit on the pages branch and do not push. `scripts/redirect_legacy_docs.py` writes the legacy refresh stubs.
- `pyproject.toml`: `version = "0.3.2"`.
