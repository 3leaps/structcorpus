#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# Public-surface scan with limensafe: the built-in public baseline, from a
# configuration written to a temporary directory at run time, plus a
# maintainer catalog kept outside this repository and passed with --catalog.
# No scan configuration is kept in the repository. The catalog is never given
# to any workflow, so nothing private can reach a GitHub runner; CI runs the
# baseline only.
#
# Scans the tracked tree at HEAD, each commit message in BASE..HEAD, the PR
# title and body when STRUCTCORPUS_SURFACE_PR_TEXT names a file, and the branch
# name. Before trusting the catalog, it must block its own canary (the alias
# of its StructcorpusCanary entity, read from the catalog at run time); the
# baseline-only scan must block a built-in sentinel instead.
#
#   LIMENSAFE_CATALOG_PATH       the catalog (catalog_id structcorpus-release); an
#                                absolute path to a regular file outside this
#                                repository and any worktree of it. Unset: warn
#                                and skip, unless STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1.
#                                Set but empty, relative, missing or inside: fail.
#   STRUCTCORPUS_LIMENSAFE_BIN       optional absolute path to limensafe.
#   STRUCTCORPUS_SURFACE_BASE        base for the commit-message scan (default
#                                origin/main); scope=release scans all of HEAD.
#   STRUCTCORPUS_SURFACE_PR_TEXT     a file with the PR title and body to scan;
#                                required when the scan is required in PR scope.
#   STRUCTCORPUS_SURFACE_SCOPE      pr (default) or release.
#   STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1  require the catalog (make pr-final,
#                                make surface-scan-release, release preflight).
#   STRUCTCORPUS_SURFACE_BASELINE_ONLY=1  scan with the built-in baseline only
#                                (CI); LIMENSAFE_CATALOG_PATH must be unset.
#   STRUCTCORPUS_SURFACE_BRANCH_NAME branch name to scan when HEAD is detached.
set -euo pipefail
for _git_var in $(compgen -e); do
  case "$_git_var" in
    GIT_COMMITTER_NAME | GIT_COMMITTER_EMAIL | GIT_AUTHOR_NAME | GIT_AUTHOR_EMAIL | GIT_CONFIG_NOSYSTEM) ;;
    GIT_*) unset "$_git_var" ;;
  esac
done
unset _git_var
export GIT_NO_REPLACE_OBJECTS=1
root="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$root"
catalog_id=structcorpus-release
baseline_id=limensafe-public-baseline-v0
canary_id=StructcorpusCanary

# fd 3 is the caller's stderr: errors stay visible even where a scan's own
# finding lines are redirected away.
exec 3>&2
die() {
  echo "error: $*" >&3
  exit 1
}

case "${STRUCTCORPUS_SURFACE_SCOPE:-pr}" in
  pr | release) ;;
  *) die 'STRUCTCORPUS_SURFACE_SCOPE must be pr or release' ;;
esac
case "${STRUCTCORPUS_SURFACE_BASELINE_ONLY:-0}" in
  0 | 1) ;;
  *) die 'STRUCTCORPUS_SURFACE_BASELINE_ONLY must be 0 or 1' ;;
esac
if [[ "${STRUCTCORPUS_SURFACE_BASELINE_ONLY:-0}" == 1 ]]; then
  [[ -z "${LIMENSAFE_CATALOG_PATH+set}" ]] || die 'the baseline-only scan requires LIMENSAFE_CATALOG_PATH to be unset'
  [[ "${STRUCTCORPUS_SURFACE_SCAN_REQUIRED:-0}" != 1 ]] || die 'the baseline-only scan cannot satisfy STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1'
  [[ "${STRUCTCORPUS_SURFACE_SCOPE:-pr}" == pr ]] || die 'the baseline-only scan is PR scope only'
  baseline_only=1
  scan_mode=(--mode ci)
  catalog_args=()
  required_catalogs="$baseline_id"
else
  if [[ -z "${LIMENSAFE_CATALOG_PATH+set}" ]]; then
    [[ "${STRUCTCORPUS_SURFACE_SCAN_REQUIRED:-0}" != 1 ]] || die 'LIMENSAFE_CATALOG_PATH is required for this gate'
    echo '[skip] surface scan: LIMENSAFE_CATALOG_PATH is not set'
    exit 0
  fi
  baseline_only=0
  scan_mode=(--mode release)
  required_catalogs="$catalog_id,$baseline_id"
  catalog="$LIMENSAFE_CATALOG_PATH"
  [[ -n "$catalog" ]] || die 'LIMENSAFE_CATALOG_PATH is set but empty'
  [[ "$catalog" == /* ]] || die 'LIMENSAFE_CATALOG_PATH must be an absolute path'
  [[ -f "$catalog" && -r "$catalog" ]] || die 'LIMENSAFE_CATALOG_PATH does not name a readable file'
  catalog_args=(--catalog "$catalog")
  common="$(git --no-replace-objects -C "$root" rev-parse --path-format=absolute --git-common-dir)"
  worktrees="$(git --no-replace-objects --git-dir="$common" worktree list --porcelain)" || die 'cannot enumerate worktrees'
  roots=("$root")
  while IFS= read -r line; do
    [[ "$line" == worktree\ * ]] || continue
    roots+=("${line#worktree }")
  done <<<"$worktrees"
  "${PYTHON:-python3}" -I "$root/scripts/surface-catalog-path.py" "$catalog" ${roots[@]+"${roots[@]}"} 2>&3 ||
    die 'the catalog location was refused'
fi

bin="${STRUCTCORPUS_LIMENSAFE_BIN:-limensafe}"
if [[ "$bin" == */* ]]; then
  [[ "$bin" == /* && -x "$bin" ]] || die 'STRUCTCORPUS_LIMENSAFE_BIN must be an absolute path to an executable'
else
  bin="$(command -v "$bin")" || die 'limensafe not found on PATH'
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/structcorpus-surface.XXXXXX")"
trap 'rc=$?; rm -rf "$work"; exit "$rc"' EXIT
config="$work/config.yaml"
cat >"$config" <<YAML
schema_version: "1.0.0"
repo:
  id: 3leaps/structcorpus
  visibility: public_oss
catalogs:
  - catalog_id: $baseline_id
    source:
      kind: builtin
      name: public-baseline
    optional: false
policy:
  block_threshold: high
  redaction_safe_output: true
YAML

scan() {
  local label="$1" rc=0
  shift
  rm -f "$work/report.json"
  "$bin" scan "$@" --config-file "$config" ${catalog_args[@]+"${catalog_args[@]}"} "${scan_mode[@]}" --include-ignored --max-file-size 4294967296 \
    >"$work/report.json" 2>"$work/scan.err" || rc=$?
  [[ "$rc" -le 1 ]] || {
    grep -v '^catalog warning: ' "$work/scan.err" | head -3 >&3 || true
    die "$label: limensafe exited $rc"
  }
  "${PYTHON:-python3}" -I - "$work/report.json" "$required_catalogs" "$label" "$rc" <<'PY'
import json, os, sys
path, required, label, rc = sys.argv[1], sys.argv[2].split(","), sys.argv[3], int(sys.argv[4])
def fail(message):
    os.write(3, (message + "\n").encode())
    sys.exit(1)
try:
    d = json.load(open(path))
    loaded = {c["catalog_id"]: c["load_status"] for c in d["scan_metadata"]["catalogs_loaded"]}
    total = d["summary"]["findings_total"]
except (OSError, ValueError, KeyError, TypeError):
    fail(f"error: {label}: limensafe report is missing or invalid")
for catalog_id in required:
    if loaded.get(catalog_id) != "ok":
        fail(f"error: {label}: catalog {catalog_id} did not load")
if (total > 0) != (rc == 1):
    fail(f"error: {label}: exit status {rc} disagrees with {total} finding(s)")
meta = d.get("scan_metadata", {})
skipped = meta.get("files_skipped_by_reason")
if not isinstance(skipped, dict):
    fail(f"error: {label}: limensafe report does not account for skipped files")
other = {k: v for k, v in skipped.items() if k != "binary_detected" and v}
if other:
    fail(f"error: {label}: files were skipped, not scanned: " + ", ".join(f"{k}={v}" for k, v in sorted(other.items())))
if meta.get("directories_skipped"):
    fail(f"error: {label}: directories were skipped, not scanned: {meta.get('directories_skipped')}")
for f in d.get("findings", []):
    loc = f.get("location", {})
    print(f"  {f.get('severity', '?')} {f.get('entity_class', '?')} {loc.get('path', '-')}:{loc.get('line', '-')}", file=sys.stderr)
if total:
    print(f"[block] {label}: {total} finding(s)", file=sys.stderr)
    sys.exit(3)
PY
  local status=$?
  [[ "$status" -ne 3 ]] || return 1
  [[ "$status" -eq 0 ]] || exit 1
  echo "[ok] $label"
}

if [[ "$baseline_only" == 1 ]]; then
  mkdir "$work/control"
  # Split so this file does not itself carry the sentinel.
  printf 'tripwire %s%s\n' DO_NOT_ COMMIT >"$work/control/control.txt"
  if scan control "$work/control" 2>"$work/control.err"; then
    die 'the baseline did not block its sentinel'
  fi
  rm -rf "$work/control"
  echo '[ok] baseline blocks its sentinel'
else
  canary="$("${PYTHON:-python3}" -I "$root/scripts/surface-canary.py" "$catalog" "$canary_id")" ||
    die 'the catalog has no usable canary'
  mkdir "$work/canary"
  printf 'tripwire %s\n' "$canary" >"$work/canary/canary.txt"
  unset canary
  if scan canary "$work/canary" 2>"$work/canary.err"; then
    die 'the catalog did not block its canary'
  fi
  "${PYTHON:-python3}" -I -c '
    import json, sys
    d = json.load(open(sys.argv[1]))
    ok = any(f.get("decision") == "block" and f.get("replacement_id") == sys.argv[2] for f in d.get("findings", []))
    sys.exit(0 if ok else "error: the canary was not blocked as " + sys.argv[2])' "$work/report.json" "$canary_id"
  rm -rf "$work/canary"
  echo '[ok] catalog blocks its canary'
fi

failed=0
mkdir "$work/tree"
"${PYTHON:-python3}" -I -B "$root/scripts/export-committed-tree.py" "$root" HEAD "$work/tree" >/dev/null 2>&3 ||
  die 'cannot export the committed tree'
scan tree "$work/tree" || failed=1
rm -rf "$work/tree"

[[ -z "${STRUCTCORPUS_SURFACE_RELEASE_BASE+x}" ]] ||
  die 'STRUCTCORPUS_SURFACE_RELEASE_BASE override is not permitted'
if [[ "${STRUCTCORPUS_SURFACE_SCOPE:-pr}" == release ]]; then
  commits="$(git --no-replace-objects -C "$root" rev-list HEAD)"
else
  base="${STRUCTCORPUS_SURFACE_BASE:-origin/main}"
  git --no-replace-objects -C "$root" rev-parse --verify --quiet "$base^{commit}" >/dev/null || die "base $base not found; fetch it or set STRUCTCORPUS_SURFACE_BASE"
  commits="$(git --no-replace-objects -C "$root" rev-list "$base..HEAD")"
fi
for sha in $commits; do
  git --no-replace-objects -C "$root" log -1 --format=%B "$sha" >"$work/message"
  scan "commit ${sha:0:12}" --commit-msg - <"$work/message" || failed=1
done

if [[ -n "${STRUCTCORPUS_SURFACE_PR_TEXT:-}" ]]; then
  [[ -f "${STRUCTCORPUS_SURFACE_PR_TEXT}" && -s "${STRUCTCORPUS_SURFACE_PR_TEXT}" ]] ||
    die 'STRUCTCORPUS_SURFACE_PR_TEXT does not name a non-empty file'
  scan 'pr text' --commit-msg - <"$STRUCTCORPUS_SURFACE_PR_TEXT" || failed=1
elif [[ "${STRUCTCORPUS_SURFACE_SCAN_REQUIRED:-0}" == 1 && "${STRUCTCORPUS_SURFACE_SCOPE:-pr}" != release ]]; then
  die 'STRUCTCORPUS_SURFACE_PR_TEXT is required here: write the PR title and body to a file and pass it'
fi

if branch="$(git --no-replace-objects -C "$root" symbolic-ref --quiet --short HEAD)"; then
  printf '%s\n' "$branch" | scan 'branch name' --branch-name - || failed=1
elif [[ -n "${STRUCTCORPUS_SURFACE_BRANCH_NAME:-}" ]]; then
  printf '%s\n' "$STRUCTCORPUS_SURFACE_BRANCH_NAME" | scan 'branch name' --branch-name - || failed=1
else
  echo '[skip] branch name: detached HEAD'
fi

[[ "$failed" -eq 0 ]] || die 'public-surface findings (run limensafe directly for locations)'
echo "[ok] surface scan: tree, $(wc -w <<<"$commits" | tr -d ' ') commit message(s)$([[ -n "${STRUCTCORPUS_SURFACE_PR_TEXT:-}" ]] && echo ', pr text')"
