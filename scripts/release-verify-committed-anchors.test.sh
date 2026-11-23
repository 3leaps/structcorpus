#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# In-tree anchor verification: no maintainer env vars; any mismatch between the
# committed public pin and either anchor fails closed. Mutations run on a
# scratch copy, never on this checkout.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
bin="${STRUCTCORPUS_DECERNOR_BIN:-$(command -v decernor || true)}"
[[ -n "$bin" && -x "$bin" ]] || {
  echo 'error: STRUCTCORPUS_DECERNOR_BIN required (absolute path to decernor >= 0.1.8)' >&2
  exit 1
}
export STRUCTCORPUS_DECERNOR_BIN="$bin"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
repo="$scratch/repo"
mkdir -p "$repo/scripts" "$repo/keys" "$repo/docs/security"
cp "$root/scripts/release-verify-committed-anchors.sh" "$root/scripts/release-decernor.sh" "$repo/scripts/"
cp "$root/keys/expected-fingerprints.txt" "$root/keys/expected-fingerprints.ndjson" "$repo/keys/"
cp "$root/docs/security/release-signing-keys.asc" "$repo/docs/security/"
cp -R "$repo/keys" "$scratch/good-keys"
check() {
  env -u STRUCTCORPUS_PGP_KEY_ID -u STRUCTCORPUS_GPG_SIGNING_FINGERPRINT -u STRUCTCORPUS_GPG_HOMEDIR \
    "$repo/scripts/release-verify-committed-anchors.sh"
}
refused() {
  local why="$1" expected="$2"
  if check >"$scratch/out" 2>&1; then
    echo "error: accepted: $why" >&2
    exit 1
  fi
  grep -qF -- "$expected" "$scratch/out" || {
    echo "error: rejected for the wrong reason: $why" >&2
    cat "$scratch/out" >&2
    exit 1
  }
  rm -rf "$repo/keys"
  cp -R "$scratch/good-keys" "$repo/keys"
  echo "[ok] refused: $why"
}
# The committed material verifies without the maintainer-only variables.
check >/dev/null
# The checker is required.
if env -u STRUCTCORPUS_DECERNOR_BIN "$repo/scripts/release-verify-committed-anchors.sh" >/dev/null 2>&1; then
  echo 'error: verification ran without STRUCTCORPUS_DECERNOR_BIN' >&2
  exit 1
fi
printf 'gpg %040d\n' 0 >"$repo/keys/expected-fingerprints.txt"
refused 'text anchor for another primary' 'text fingerprint anchor differs'
printf '%s\nminisign %064d\n' "$(cat "$scratch/good-keys/expected-fingerprints.txt")" 0 >"$repo/keys/expected-fingerprints.txt"
refused 'extra text anchor line' 'text fingerprint anchor differs'
sed 's/"key_role":"primary"/"key_role":"subkey"/' "$scratch/good-keys/expected-fingerprints.ndjson" >"$repo/keys/expected-fingerprints.ndjson"
refused 'mutated NDJSON anchor' 'NDJSON fingerprint anchor differs'
cat "$scratch/good-keys/expected-fingerprints.ndjson" "$scratch/good-keys/expected-fingerprints.ndjson" >"$repo/keys/expected-fingerprints.ndjson"
refused 'duplicated NDJSON anchor' 'NDJSON fingerprint anchor differs'
rm "$repo/keys/expected-fingerprints.ndjson"
refused 'missing NDJSON anchor' 'missing or not a nonempty regular file'
ln -s "$scratch/good-keys/expected-fingerprints.txt" "$repo/keys/expected-fingerprints.txt.link"
rm "$repo/keys/expected-fingerprints.txt"
mv "$repo/keys/expected-fingerprints.txt.link" "$repo/keys/expected-fingerprints.txt"
refused 'symlinked text anchor' 'missing or not a nonempty regular file'
check >/dev/null
echo '[ok] committed-anchor verification uses only in-tree material'
