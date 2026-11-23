#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# sync-changelog-links.sh - Sync CHANGELOG compare-link footers to VERSION
#
# Usage: ./scripts/sync-changelog-links.sh
#
# Updates the Keep a Changelog footer links after VERSION is bumped:
# - [Unreleased] compares v<VERSION>...HEAD
# - [VERSION] compares v<previous>...v<VERSION>
# The [Unreleased] label keeps its existing capitalization.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION_FILE="${REPO_ROOT}/VERSION"
CHANGELOG_FILE="${REPO_ROOT}/CHANGELOG.md"

if [[ ! -f "$VERSION_FILE" ]]; then
  echo "[!!] VERSION file not found" >&2
  exit 1
fi

if [[ ! -f "$CHANGELOG_FILE" ]]; then
  echo "[!!] CHANGELOG.md not found" >&2
  exit 1
fi

VERSION=$(tr -d '[:space:]' <"$VERSION_FILE")

version_gt() {
  local left_major left_minor left_patch
  local right_major right_minor right_patch

  IFS=. read -r left_major left_minor left_patch <<<"$1"
  IFS=. read -r right_major right_minor right_patch <<<"$2"

  if ((left_major != right_major)); then
    ((left_major > right_major))
    return
  fi
  if ((left_minor != right_minor)); then
    ((left_minor > right_minor))
    return
  fi
  ((left_patch > right_patch))
}

if [[ -z "$VERSION" ]]; then
  echo "[!!] VERSION file is empty" >&2
  exit 1
fi

if [[ ! "$VERSION" =~ ^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$ ]]; then
  echo "[!!] Invalid version format: $VERSION (expected x.y.z)" >&2
  exit 1
fi

UNRELEASED_COUNT=$(grep -ciE '^\[unreleased\]:' "$CHANGELOG_FILE" || true)
if [[ "$UNRELEASED_COUNT" != 1 ]]; then
  echo "[!!] CHANGELOG.md must have exactly one [Unreleased] compare-link footer" >&2
  exit 1
fi
UNRELEASED_LINE=$(grep -iE '^\[unreleased\]:' "$CHANGELOG_FILE")

if [[ ! "$UNRELEASED_LINE" =~ ^\[([Uu]nreleased)\]:[[:space:]]*(https://.*/compare/)v([0-9]+\.[0-9]+\.[0-9]+)\.\.\.HEAD$ ]]; then
  echo "[!!] Could not parse [Unreleased] compare-link footer:" >&2
  echo "    $UNRELEASED_LINE" >&2
  echo "    Expected: [Unreleased]: https://<host>/<owner>/<repo>/compare/vX.Y.Z...HEAD" >&2
  exit 1
fi

LABEL="${BASH_REMATCH[1]}"
COMPARE_PREFIX="${BASH_REMATCH[2]}"
if [[ "$COMPARE_PREFIX" != "https://github.com/3leaps/structcorpus/compare/" ]]; then
  echo "[!!] [Unreleased] footer does not point at this repository: $UNRELEASED_LINE" >&2
  exit 1
fi
PREVIOUS_VERSION="${BASH_REMATCH[3]}"
NEW_UNRELEASED="[${LABEL}]: ${COMPARE_PREFIX}v${VERSION}...HEAD"
NEW_VERSION_DEF="[${VERSION}]: ${COMPARE_PREFIX}v${PREVIOUS_VERSION}...v${VERSION}"

HAS_VERSION_DEF=0
if grep -qE "^\[${VERSION//./\\.}\]:" "$CHANGELOG_FILE"; then
  HAS_VERSION_DEF=1
fi

# Report success only for content the release-surface guard accepts, so a
# wrong destination is never described as synced. A rewrite is validated while
# still staged, so a refusal never leaves CHANGELOG.md modified.
# shellcheck source=scripts/release-guard-release-surfaces.sh
source "${SCRIPT_DIR}/release-guard-release-surfaces.sh"
confirm_synced() {
  reject_nul "$1" || exit 1
  validate_release_surfaces "$VERSION" "$(cat "$1")" >/dev/null || {
    echo "[!!] CHANGELOG footers would fail the release-surface guard; CHANGELOG.md left unchanged" >&2
    exit 1
  }
}

if [[ "$PREVIOUS_VERSION" == "$VERSION" && "$HAS_VERSION_DEF" -eq 1 ]]; then
  confirm_synced "$CHANGELOG_FILE"
  echo "[ok] CHANGELOG compare links already synced for $VERSION"
  exit 0
fi

if [[ "$PREVIOUS_VERSION" == "$VERSION" ]]; then
  echo "[!!] [Unreleased] already starts at $VERSION, but [$VERSION] is missing" >&2
  echo "    Cannot infer the previous release for the [$VERSION] compare link." >&2
  exit 1
fi

if ! version_gt "$VERSION" "$PREVIOUS_VERSION"; then
  echo "[!!] Refusing to sync CHANGELOG compare links backwards: $PREVIOUS_VERSION -> $VERSION" >&2
  exit 1
fi

TMP_FILE=$(mktemp "${CHANGELOG_FILE}.XXXXXX")
trap 'rm -f "$TMP_FILE"' EXIT

awk \
  -v version="$VERSION" \
  -v new_unreleased="$NEW_UNRELEASED" \
  -v new_version_def="$NEW_VERSION_DEF" \
  -v has_version_def="$HAS_VERSION_DEF" \
  '
    BEGIN {
        version_label = "[" version "]:"
    }

    tolower(substr($0, 1, 13)) == "[unreleased]:" {
        print new_unreleased
        if (has_version_def == 0) {
            print new_version_def
        }
        next
    }

    index($0, version_label) == 1 {
        print new_version_def
        next
    }

    {
        print
    }
    ' "$CHANGELOG_FILE" >"$TMP_FILE"

confirm_synced "$TMP_FILE"
mv "$TMP_FILE" "$CHANGELOG_FILE"
trap - EXIT

if [[ "$HAS_VERSION_DEF" -eq 1 ]]; then
  echo "[ok] CHANGELOG compare links updated for $VERSION"
else
  echo "[ok] CHANGELOG compare links added: $PREVIOUS_VERSION -> $VERSION"
fi
