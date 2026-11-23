#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# Controls for sync-changelog-links.sh: a version bump rewrites the footer
# links, a synced changelog is left alone, and unsafe inputs are refused
# without modifying CHANGELOG.md.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/repo/scripts"
cp "$root/scripts/sync-changelog-links.sh" "$root/scripts/release-guard-release-surfaces.sh" "$scratch/repo/scripts/"
changelog="$scratch/repo/CHANGELOG.md"
base='# Changelog

## [Unreleased]

## [0.2.0] - 2026-12-01

- A record.

## [0.1.0] - 2026-11-17

- An earlier record.

[Unreleased]: https://github.com/3leaps/structcorpus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/3leaps/structcorpus/releases/tag/v0.1.0'

run() { "$scratch/repo/scripts/sync-changelog-links.sh"; }
refused() {
  local why="$1" before
  before="$(cat "$changelog")"
  if run >"$scratch/out" 2>&1; then
    echo "error: accepted: $why" >&2
    exit 1
  fi
  [[ "$(cat "$changelog")" == "$before" ]] || {
    echo "error: CHANGELOG.md modified on refusal: $why" >&2
    exit 1
  }
  [[ -z "$(find "$scratch/repo" -name 'CHANGELOG.md.*')" ]] || {
    echo "error: temporary file left behind: $why" >&2
    exit 1
  }
  echo "[ok] refused: $why"
}

printf '%s\n' "$base" >"$changelog"
echo 0.2.0 >"$scratch/repo/VERSION"
run >/dev/null
grep -qx '\[Unreleased\]: https://github.com/3leaps/structcorpus/compare/v0.2.0...HEAD' "$changelog"
grep -qx '\[0.2.0\]: https://github.com/3leaps/structcorpus/compare/v0.1.0...v0.2.0' "$changelog"
grep -qx '\[0.1.0\]: https://github.com/3leaps/structcorpus/releases/tag/v0.1.0' "$changelog"
echo '[ok] bump adds the version link and moves [Unreleased]'
synced="$(cat "$changelog")"
run | grep -q 'already synced'
[[ "$(cat "$changelog")" == "$synced" ]]
echo '[ok] synced changelog is unchanged'

echo 0.1.0 >"$scratch/repo/VERSION"
refused 'backwards sync'
echo 0.2 >"$scratch/repo/VERSION"
refused 'malformed VERSION'
echo 0.3.0 >"$scratch/repo/VERSION"
printf '%s\n' "$base" | sed '/^\[Unreleased\]:/d' >"$changelog"
refused 'missing [Unreleased] footer'
printf '%s\n' "$base" | sed 's|^\[Unreleased\]: .*|[Unreleased]: https://github.com/3leaps/structcorpus/compare/v0.1.0...main|' >"$changelog"
refused 'unparseable [Unreleased] footer'
printf '%s\n%s\n' "$base" '[unreleased]: https://github.com/3leaps/structcorpus/compare/v0.1.0...HEAD' >"$changelog"
refused 'duplicate [Unreleased] footers'
printf '%s\n' "$base" | sed 's|3leaps/structcorpus/compare/v0.1.0...HEAD|3leaps/other/compare/v0.1.0...HEAD|' >"$changelog"
refused '[Unreleased] footer for another repository'
echo 0.1.0 >"$scratch/repo/VERSION"
printf '%s\n' "$base" | sed 's|^\[0.1.0\]: .*|[0.1.0]: https://github.com/3leaps/structcorpus/releases/tag/v9.9.9|' >"$changelog"
refused 'already-synced footer with a wrong version destination'
# Refusals found only after rewriting the links must still leave the file
# untouched: the rewrite is validated while staged.
echo 0.2.0 >"$scratch/repo/VERSION"
printf '%s\n' "$base" | sed '/^## \[0.2.0\]/d' >"$changelog"
refused 'bump whose version heading is missing'
printf '%s\n%s\n' "$base" '[0.2.0]: https://github.com/3leaps/structcorpus/compare/v0.1.0...v0.2.0' |
  sed 's|^\[Unreleased\]: .*|[Unreleased]: https://github.com/3leaps/structcorpus/compare/v0.1.0...HEAD|' >"$changelog"
printf '%s\n' '[0.2.0]: https://github.com/3leaps/structcorpus/compare/v0.1.0...v0.2.0' >>"$changelog"
refused 'bump with duplicate current-version definitions'
echo '[ok] sync-changelog-links controls passed'
