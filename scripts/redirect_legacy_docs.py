#!/usr/bin/env python3
"""Write HTML refresh stubs for the pre-split documentation URLs.

Reads the published page list from the local ``gh-pages`` branch and writes
``index.html`` stubs under ``--dest``. It does not check out, commit, or
push that branch.

Mapping:

- ``/vX.Y/spatial|blueprint|api/...`` and ``/latest/...`` of those trees
  go to ``/gigameter-research/geofencing/<version>/...``
- ``/vX.Y/adr/...`` and ``/latest/adr/...`` go to ``/gigameter-research/adr/...``
- ``/vX.Y/connectivity/...`` goes to ``/gigameter-research/outage/connectivity/...``
- ``/vX.Y/diagnostics/...`` goes to ``/gigameter-research/routing/diagnostics/...``
- a version root goes to ``/gigameter-research/geofencing/<version>/``
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

SITE = "/gigameter-research"
VERSIONS = ("v0.2", "v0.3", "latest")


def pages(repo: Path, version: str) -> list[str]:
    """Return directory-URL paths ('' for the version root) published at ``version``."""
    source = "v0.3" if version == "latest" else version
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "gh-pages", source],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    found: list[str] = []
    for line in out.stdout.splitlines():
        prefix = f"{source}/"
        if not line.startswith(prefix) or not line.endswith("/index.html"):
            continue
        rel = line[len(prefix) : -len("index.html")].rstrip("/")
        found.append(rel)
    if "" not in found:
        found.append("")
    return found


def target(version: str, rel: str) -> str:
    if rel == "adr" or rel.startswith("adr/"):
        return f"{SITE}/{rel}/"
    if rel == "connectivity" or rel.startswith("connectivity/"):
        return f"{SITE}/outage/{rel}/"
    if rel == "diagnostics" or rel.startswith("diagnostics/"):
        return f"{SITE}/routing/{rel}/"
    suffix = f"{rel}/" if rel else ""
    return f"{SITE}/geofencing/{version}/{suffix}"


def stub(url: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f'  <link rel="canonical" href="{url}">\n'
        f'  <meta http-equiv="refresh" content="0; url={url}">\n'
        "  <title>Redirect</title>\n"
        "</head>\n"
        "<body>\n"
        f'  <p><a href="{url}">Continue</a></p>\n'
        "</body>\n"
        "</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()
    dest = args.dest.resolve()
    repo = args.repo.resolve()
    for version in VERSIONS:
        for rel in pages(repo, version):
            folder = dest / version if rel == "" else dest / version / rel
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "index.html").write_text(stub(target(version, rel)))
            print(f"{version}/{rel or ''} -> {target(version, rel)}")


if __name__ == "__main__":
    main()
