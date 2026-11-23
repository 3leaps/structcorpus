#!/usr/bin/env bash
# Verify the committed public pin against both fingerprint anchors with the
# designated checker. In-tree material only; no maintainer env vars.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$root"
# shellcheck source=scripts/release-decernor.sh
source "$root/scripts/release-decernor.sh"
resolve_release_decernor ceremony || {
  echo 'error: trusted Decernor identity/version check failed' >&2
  exit 1
}
release_verify_gpg_anchors keys/expected-fingerprints.txt keys/expected-fingerprints.ndjson \
  docs/security/release-signing-keys.asc || {
  echo 'error: committed public pin does not match the fingerprint anchors' >&2
  exit 1
}
echo '[ok] committed public pin matches both fingerprint anchors'
