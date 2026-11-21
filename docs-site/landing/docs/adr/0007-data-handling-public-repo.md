# 0007. Public-repo data handling

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

The repository is public. Ledgers contain facility and device identifiers, radio identifiers, and coordinates.

## Decision

Do not put real school IDs, device IDs, SSIDs, BSSIDs, coordinates, or ledger country codes in code, tests, docs, pull requests, issues, or rules. Keep `data/` local and gitignored. Use synthetic fixtures. Anonymise worked examples.

## Evidence

- `README.md`, Data Handling: `data/`, CSV, and Parquet stay gitignored; facility location is the Wi-Fi result only.
- `.gitignore` ignores `data/`, `*.csv`, and `*.parquet`.
- [Worked Examples](/gigameter-research/geofencing/latest/spatial/examples/) describe replayed cases without shipping a ledger.
