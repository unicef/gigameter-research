# 0001. Version the agent rules

- Status: Accepted
- Date: 2026-11-18
- Deciders: Utku Can Ozturk

## Context

Agent rules lived only under gitignored `.cursor/`. The telemetry catalogue was applied to every chat, which spent context on field reference the docs are meant to hold.

## Decision

Version only the slim, scrubbed rules under `.cursor/rules/`. Those files carry no internal names, IDs, URLs, credentials, or dated filenames. Leave the rest of `.cursor/` ignored. Keep one short rule always on. Point SQL, ping, and NDT7 work at a docs data-dictionary page instead of sending the full catalogue into every chat. Commit the project rules. Do not publish them in MkDocs. An optional root `AGENTS.md` may point other agents at the same rules.

## Consequences

`.gitignore` still ignores the whole `.cursor/` directory, so the rules are not in git until that ignore is narrowed. The data-dictionary page is not written yet. Raw rule drafts stay off the published site.

## Alternatives considered

Leaving the full telemetry catalogue always on kept the field list in every chat.

## Evidence

- `.gitignore` ignores `.cursor/`.
- [ADR 0007](0007-data-handling-public-repo.md) is the public-repo constraint on what a versioned rule may contain.
- The MkDocs configs under `docs-site/` publish each site's `docs/` directory only.
