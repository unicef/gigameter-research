#!/usr/bin/env bash
# Build, migrate, and publish the per-track docs.
# build-all never touches gh-pages.
# migrate-gh-pages and publish commit on DOCS_PAGES_BRANCH (default: gh-pages)
# and print the push command. They never push, and they never run mkdocs gh-deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PREVIEW_BRANCH="preview/per-track-sites"
PAGES_BRANCH="${DOCS_PAGES_BRANCH:-gh-pages}"
SITE="$ROOT/site"
CONFIG_LANDING="docs-site/landing/mkdocs.yml"
CONFIG_GEO="docs-site/geofencing/mkdocs.yml"
CONFIG_OUTAGE="docs-site/outage/mkdocs.yml"
CONFIG_ROUTING="docs-site/routing/mkdocs.yml"

WT=""
BUILD_TMP=""

die() {
  echo "docs.sh: $*" >&2
  if [[ -n "${WT:-}" ]]; then
    remove_worktree "$WT"
    WT=""
  fi
  if [[ -n "${BUILD_TMP:-}" ]]; then
    rm -rf "$BUILD_TMP"
  fi
  exit 1
}

resolve_mkdocs() {
  if command -v mkdocs >/dev/null 2>&1; then
    MKDOCS=(mkdocs)
  elif [[ -x "$ROOT/.venv/bin/mkdocs" ]]; then
    MKDOCS=("$ROOT/.venv/bin/mkdocs")
  elif [[ -x /tmp/gigameter-docs-venv/bin/mkdocs ]]; then
    MKDOCS=(/tmp/gigameter-docs-venv/bin/mkdocs)
  else
    die "mkdocs not found on PATH, in .venv, or in /tmp/gigameter-docs-venv"
  fi
}

mike_local() {
  # $1 config, remaining args are mike arguments. Branch is forced off gh-pages.
  local config="$1"
  shift
  local branch=""
  local prev=""
  for arg in "$@"; do
    if [[ "$prev" == "--branch" || "$prev" == "-b" ]] && [[ "$arg" == "gh-pages" ]]; then
      die "refusing to deploy to gh-pages"
    fi
    if [[ "$arg" == "--push" || "$arg" == "-p" ]]; then
      die "refusing to push"
    fi
    if [[ "$prev" == "--branch" || "$prev" == "-b" ]]; then
      branch="$arg"
    fi
    prev="$arg"
  done
  [[ "$branch" == "$PREVIEW_BRANCH" ]] || die "local mike deploy must use --branch $PREVIEW_BRANCH"
  command -v mike >/dev/null 2>&1 || die "mike not found on PATH"
  mike "$@" -F "$config"
}

build_strict() {
  local config="$1"
  local dest="$2"
  resolve_mkdocs
  rm -rf "$dest"
  "${MKDOCS[@]}" build -f "$config" --strict -d "$dest"
}

# rsync a plain site into dest. Protected directories stay put, including any
# root versions.json. mkdocs gh-deploy is never used: it would replace the branch.
rsync_site() {
  local src="$1"
  local dest="$2"
  shift 2
  command -v rsync >/dev/null 2>&1 || die "rsync not found"
  rsync -a --delete \
    --exclude '/geofencing/' \
    --exclude '/outage/' \
    --exclude '/routing/' \
    --exclude '/v0.2/' \
    --exclude '/v0.3/' \
    --exclude '/latest/' \
    --exclude '/.nojekyll' \
    --exclude '/.git' \
    --exclude '/versions.json' \
    "$@" \
    "${src}/" "${dest}/"
}

open_pages_worktree() {
  git show-ref --verify --quiet "refs/heads/$PAGES_BRANCH" || die "no local branch $PAGES_BRANCH"
  local current
  current="$(git branch --show-current)"
  if [[ "$current" == "$PAGES_BRANCH" ]]; then
    die "$PAGES_BRANCH is checked out in this worktree"
  fi
  WT="$(mktemp -d /tmp/gigameter-pages.XXXXXX)"
  git worktree add "$WT" "$PAGES_BRANCH" >/dev/null
}

remove_worktree() {
  local wt="$1"
  if [[ -n "$wt" && -d "$wt" ]]; then
    git worktree remove --force "$wt" >/dev/null 2>&1 || rm -rf "$wt"
    git worktree prune >/dev/null 2>&1 || true
  fi
}

assert_root_versions_absent() {
  local wt="$1"
  if [[ -f "$wt/versions.json" ]]; then
    die "refusing to leave a versions.json at the site root"
  fi
}

assert_root_versions_diff() {
  local wt="$1"
  local allow_delete="${2:-}"
  local status
  status="$(git -C "$wt" diff --cached --name-status -- ':(top)versions.json' || true)"
  [[ -z "$status" ]] && return 0
  if [[ "$allow_delete" == "delete" && "$status" == D* ]]; then
    return 0
  fi
  die "refusing to commit a root versions.json (${status})"
}

assert_staged_prefixes() {
  local wt="$1"
  shift
  local path ok prefix
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    ok=0
    for prefix in "$@"; do
      if [[ "$path" == "$prefix" || "$path" == "$prefix"* ]]; then
        ok=1
        break
      fi
    done
    [[ "$ok" == 1 ]] || die "staged path outside this publish: $path"
  done < <(git -C "$wt" diff --cached --name-only)
}

commit_worktree() {
  local wt="$1"
  local message="$2"
  if git -C "$wt" diff --cached --quiet; then
    echo "Nothing changed on ${PAGES_BRANCH}; no commit."
    return 0
  fi
  git -C "$wt" commit -m "$(cat <<EOF
$message

EOF
)" >/dev/null
  echo "Committed on ${PAGES_BRANCH}."
  echo "Push with:"
  echo "  git push origin ${PAGES_BRANCH}"
}

seed_v02_versions() {
  local wt="$1"
  python3 - "$wt" <<'PY'
import json
import sys
from pathlib import Path

wt = Path(sys.argv[1])
raw = json.loads((wt / "versions.json").read_text())
kept = [item for item in raw if item.get("version") == "v0.2"]
if len(kept) != 1:
    raise SystemExit("root versions.json must contain one v0.2 entry")
kept[0]["aliases"] = []
dest = wt / "geofencing"
dest.mkdir(exist_ok=True)
(dest / "versions.json").write_text(json.dumps(kept, indent=2) + "\n")
PY
}

migrate_gh_pages() {
  local real_sha build=""
  real_sha="$(git rev-parse gh-pages)"
  open_pages_worktree
  local wt="$WT"
  trap 'status=$?; remove_worktree "$wt"; [[ -z "${build:-}" ]] || rm -rf "$build"; exit "$status"' RETURN
  [[ -d "$wt/v0.2" ]] || die "v0.2 is not at the root; migrate has already run"
  [[ -f "$wt/versions.json" ]] || die "root versions.json is missing"
  seed_v02_versions "$wt"
  git -C "$wt" mv v0.2 geofencing/v0.2
  git -C "$wt" rm -r --quiet -- v0.3 latest versions.json
  build="$(mktemp -d /tmp/gigameter-landing.XXXXXX)"
  build_strict "$CONFIG_LANDING" "$build"
  rsync_site "$build" "$wt"
  [[ -f "$wt/.nojekyll" ]] || : > "$wt/.nojekyll"
  python3 "$ROOT/scripts/redirect_legacy_docs.py" --dest "$wt" --repo "$ROOT" >/dev/null
  assert_root_versions_absent "$wt"
  git -C "$wt" add -A -- . ':(exclude,top)versions.json'
  git -C "$wt" add -- geofencing/versions.json
  assert_root_versions_absent "$wt"
  assert_root_versions_diff "$wt" delete
  commit_worktree "$wt" "docs: migrate the published site onto per-track paths"
  [[ "$(git rev-parse gh-pages)" == "$real_sha" || "$PAGES_BRANCH" == "gh-pages" ]] \
    || die "gh-pages moved during migrate"
}

publish_target() {
  local target="$1"
  local real_sha build=""
  real_sha="$(git rev-parse gh-pages)"
  open_pages_worktree
  local wt="$WT"
  trap 'status=$?; remove_worktree "$wt"; [[ -z "${build:-}" ]] || rm -rf "$build"; exit "$status"' RETURN
  case "$target" in
    landing)
      build="$(mktemp -d /tmp/gigameter-landing.XXXXXX)"
      build_strict "$CONFIG_LANDING" "$build"
      rsync_site "$build" "$wt"
      git -C "$wt" add -A -- . ':!geofencing' ':!outage' ':!routing' ':!v0.2' ':!v0.3' ':!latest' ':!.nojekyll' ':(exclude,top)versions.json'
      assert_root_versions_absent "$wt"
      assert_root_versions_diff "$wt"
      ;;
    outage)
      build="$(mktemp -d /tmp/gigameter-outage.XXXXXX)"
      build_strict "$CONFIG_OUTAGE" "$build"
      mkdir -p "$wt/outage"
      rsync -a --delete "${build}/" "${wt}/outage/"
      git -C "$wt" add -- outage
      assert_staged_prefixes "$wt" "outage/"
      ;;
    routing)
      build="$(mktemp -d /tmp/gigameter-routing.XXXXXX)"
      build_strict "$CONFIG_ROUTING" "$build"
      mkdir -p "$wt/routing"
      rsync -a --delete "${build}/" "${wt}/routing/"
      git -C "$wt" add -- routing
      assert_staged_prefixes "$wt" "routing/"
      ;;
    redirects)
      python3 "$ROOT/scripts/redirect_legacy_docs.py" --dest "$wt" --repo "$ROOT" >/dev/null
      git -C "$wt" add -- v0.2 v0.3 latest
      assert_staged_prefixes "$wt" "v0.2/" "v0.3/" "latest/"
      ;;
    *)
      die "unknown publish target: $target"
      ;;
  esac
  assert_root_versions_absent "$wt"
  commit_worktree "$wt" "docs: publish the ${target} site"
  [[ "$(git rev-parse gh-pages)" == "$real_sha" || "$PAGES_BRANCH" == "gh-pages" ]] \
    || die "gh-pages moved during publish"
}

cmd="${1:-}"
case "$cmd" in
  build-all)
    if git show-ref --verify --quiet "refs/heads/$PREVIEW_BRANCH"; then
      git branch -D "$PREVIEW_BRANCH"
    fi
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    build_strict "$CONFIG_LANDING" "$tmp/landing"
    build_strict "$CONFIG_GEO" "$tmp/geofencing-strict"
    build_strict "$CONFIG_OUTAGE" "$tmp/outage"
    build_strict "$CONFIG_ROUTING" "$tmp/routing"

    pages_sha="$(git rev-parse gh-pages)"
    mike_local "$CONFIG_GEO" deploy --ignore-remote-status --branch "$PREVIEW_BRANCH" \
      --deploy-prefix geofencing --update-aliases --title "v0.3" v0.3 latest
    mike_local "$CONFIG_GEO" set-default --ignore-remote-status --branch "$PREVIEW_BRANCH" \
      --deploy-prefix geofencing latest
    [[ "$(git rev-parse gh-pages)" == "$pages_sha" ]] || die "gh-pages moved during the local deploy"
    rm -rf docs-site/geofencing/site docs-site/outage/site docs-site/routing/site docs-site/landing/site

    rm -rf "$SITE"
    mkdir -p "$SITE"
    git archive "$PREVIEW_BRANCH" | tar -x -C "$SITE"
    git archive gh-pages v0.2 | tar -x -C "$SITE/geofencing"
    python3 - <<'PY'
import json
from pathlib import Path
path = Path("site/geofencing/versions.json")
versions = json.loads(path.read_text())
if not any(item.get("version") == "v0.2" for item in versions):
    versions.append({"version": "v0.2", "title": "v0.2", "aliases": []})
path.write_text(json.dumps(versions, indent=2) + "\n")
PY
    cp -a "$tmp/landing/." "$SITE/"
    mkdir -p "$SITE/outage" "$SITE/routing"
    cp -a "$tmp/outage/." "$SITE/outage/"
    cp -a "$tmp/routing/." "$SITE/routing/"
    python3 scripts/redirect_legacy_docs.py --dest "$SITE" --repo "$ROOT"
    touch "$SITE/.nojekyll"
    if [[ -f "$SITE/versions.json" ]]; then
      die "site/versions.json must not exist"
    fi
    echo "Combined tree is in site/ (gitignored)."
    ;;
  migrate-gh-pages)
    migrate_gh_pages
    ;;
  publish)
    case "${2:-}" in
      landing|outage|routing|redirects) publish_target "$2" ;;
      *) die "usage: scripts/docs.sh publish <landing|outage|routing|redirects>" ;;
    esac
    ;;
  serve-landing)
    resolve_mkdocs
    "${MKDOCS[@]}" serve -f "$CONFIG_LANDING"
    ;;
  serve-geofencing)
    resolve_mkdocs
    "${MKDOCS[@]}" serve -f "$CONFIG_GEO"
    ;;
  serve-outage)
    resolve_mkdocs
    "${MKDOCS[@]}" serve -f "$CONFIG_OUTAGE"
    ;;
  serve-routing)
    resolve_mkdocs
    "${MKDOCS[@]}" serve -f "$CONFIG_ROUTING"
    ;;
  *)
    echo "usage: scripts/docs.sh build-all | migrate-gh-pages | publish <landing|outage|routing|redirects> | serve-landing | serve-geofencing | serve-outage | serve-routing" >&2
    echo "DOCS_PAGES_BRANCH selects the pages branch (default: gh-pages)." >&2
    exit 2
    ;;
esac
