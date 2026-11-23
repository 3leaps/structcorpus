#!/usr/bin/env bash
# Test the public-pin precursor targets with synthetic keys and exports only.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
fixture="$(mktemp -d)"
cleanup() {
  local home
  for home in "$fixture/home" "$fixture/other-home/.gnupg" "$fixture/repo/in-repo-home"; do
    [[ -d "$home" ]] && gpgconf --homedir "$home" --kill all >/dev/null 2>&1 || true
  done
  rm -rf "$fixture" 2>/dev/null || true
}
trap cleanup EXIT
mkdir -p "$fixture/repo/scripts" "$fixture/repo/docs" "$fixture/repo/config/release" "$fixture/home" "$fixture/other-home/.gnupg"
chmod 700 "$fixture/home" "$fixture/other-home" "$fixture/other-home/.gnupg"
cp "$root/Makefile" "$root/VERSION" "$fixture/repo/"
cp "$root/config/release/fingerprint-record.v0.schema.json" "$fixture/repo/config/release/"
cp "$root/scripts/"{release-decernor.sh,release-export-pin.sh,release-validate-pin.sh,release-insert-anchors.sh,install-release-anchors.sh,release-verify-committed-anchors.sh,validate-release-anchors.sh} "$fixture/repo/scripts/"
if [[ -z "${STRUCTCORPUS_DECERNOR_BIN:-}" ]]; then
  if [[ "${CI:-}" == true ]]; then
    echo 'error: STRUCTCORPUS_DECERNOR_BIN required in CI' >&2
    exit 1
  fi
  STRUCTCORPUS_DECERNOR_BIN="$(command -v decernor)" || {
    echo 'error: STRUCTCORPUS_DECERNOR_BIN required (absolute path to decernor >= 0.1.8)' >&2
    exit 1
  }
fi
bin="$STRUCTCORPUS_DECERNOR_BIN"
export STRUCTCORPUS_DECERNOR_BIN="$bin"
export STRUCTCORPUS_GPG_HOMEDIR="$fixture/home"
gpg --homedir "$fixture/home" --batch --pinentry-mode loopback --passphrase '' \
  --quick-gen-key 'Synthetic signing <signing@example.invalid>' ed25519 cert 1d >/dev/null 2>&1
primary="$(gpg --homedir "$fixture/home" --batch --with-colons --fingerprint --list-keys | awk -F: '$1 == "fpr" { print $10; exit }')"
gpg --homedir "$fixture/home" --batch --pinentry-mode loopback --passphrase '' \
  --quick-add-key "$primary" ed25519 sign 1d >/dev/null 2>&1
selector="$(gpg --homedir "$fixture/home" --batch --with-colons --with-subkey-fingerprint --list-keys | awk -F: '$1 == "sub" { subkey=1; next } subkey && $1 == "fpr" { print $10 "!"; exit }')"
export STRUCTCORPUS_GPG_SIGNING_FINGERPRINT="$primary" STRUCTCORPUS_PGP_KEY_ID="$selector"
unset STRUCTCORPUS_RELEASE_TAG STRUCTCORPUS_TAG_MESSAGE_DIR || true

run() { make --no-print-directory -s -C "$fixture/repo" "$@"; }
pin_times() {
  if [[ "$(uname -s)" == Darwin ]]; then
    stat -f '%m:%c' "$1"
  else
    stat -c '%Y:%Z' "$1"
  fi
}
fail() {
  local reason="$1"
  shift
  if "$@" >"$fixture/output" 2>&1; then
    echo "error: expected rejection: $reason" >&2
    exit 1
  fi
  grep -q "$reason" "$fixture/output" || {
    echo "error: missing named rejection: $reason" >&2
    cat "$fixture/output" >&2
    exit 1
  }
}
pin="$fixture/repo/docs/security/release-signing-keys.asc"
anchors="$fixture/repo/keys/expected-fingerprints.txt"
anchors_ndjson="$fixture/repo/keys/expected-fingerprints.ndjson"
fail 'public GPG pin' run release-validate-pin
fail 'public GPG pin' run release-insert-anchors
fail 'public GPG pin required' "$fixture/repo/scripts/release-insert-anchors.sh"
fail 'committed fingerprint anchors missing' "$fixture/repo/scripts/validate-release-anchors.sh"
[[ ! -e "$pin" ]]
# A GPG home inside the repository is refused before any export, so private
# GPG state can never be created under the working tree.
mkdir -m 700 "$fixture/repo/in-repo-home"
cp -R "$fixture/home/." "$fixture/repo/in-repo-home/"
fail 'GPG home must be outside the repository' env STRUCTCORPUS_GPG_HOMEDIR="$fixture/repo/in-repo-home" make --no-print-directory -s -C "$fixture/repo" release-export-pin
[[ ! -e "$pin" ]]
rm -rf "$fixture/repo/in-repo-home"
bash -c 'make --no-print-directory -s -C "$1" release-export-pin' bash "$fixture/repo" >"$fixture/output"
[[ -s "$pin" ]]
# Distinct old mtime catches a same-second touch despite stat's second resolution.
touch -t 202001010000 "$pin"
cp "$pin" "$fixture/pin-copy"
before="$(pin_times "$pin")"
env -u STRUCTCORPUS_GPG_HOMEDIR make --no-print-directory -s -C "$fixture/repo" release-validate-pin >"$fixture/output"
bash -c 'make --no-print-directory -s -C "$1" release-validate-pin' bash "$fixture/repo" >"$fixture/output"
if command -v zsh >/dev/null 2>&1; then
  zsh -c 'make --no-print-directory -s -C "$1" release-validate-pin' zsh "$fixture/repo" >"$fixture/output"
  # shellcheck disable=SC2016 # The nested zsh expands $1.
  fail 'public pin already exists' zsh -c 'make --no-print-directory -s -C "$1" release-export-pin' zsh "$fixture/repo"
elif [[ "$(uname -s)" == Darwin ]]; then
  echo 'error: zsh required for macOS release precursor test' >&2
  exit 1
else
  echo '[skip] zsh unavailable; bash-to-make coverage passed'
fi
cmp "$pin" "$fixture/pin-copy"
after="$(pin_times "$pin")"
[[ "$before" == "$after" ]] || {
  echo 'error: existing public pin timestamp changed' >&2
  exit 1
}
fail 'public pin already exists' run release-export-pin
cmp "$pin" "$fixture/pin-copy"
fail 'trusted Decernor identity' env STRUCTCORPUS_DECERNOR_BIN=decernor make --no-print-directory -s -C "$fixture/repo" release-validate-pin
fail 'trusted Decernor' env -u STRUCTCORPUS_DECERNOR_BIN DECERNOR_BIN="$bin" make --no-print-directory -s -C "$fixture/repo" release-validate-pin
fail 'trusted Decernor' env -u STRUCTCORPUS_DECERNOR_BIN DECERNOR_BIN="$bin" make --no-print-directory -s -C "$fixture/repo" release-export-pin
[[ ! -e "$anchors" ]]
other_digit=A
[[ "${primary: -1}" == A && "${selector: -2:1}" == A ]] && other_digit=B
wrong_primary="${primary%?}${other_digit}"
[[ "$wrong_primary" != "$primary" ]] || wrong_primary="${primary%?}B"
wrong_subkey="${selector%??}${other_digit}!"
[[ "$wrong_subkey" != "$selector" ]] || wrong_subkey="${selector%??}B!"
fail 'approved primary' env STRUCTCORPUS_GPG_SIGNING_FINGERPRINT="$wrong_primary" make --no-print-directory -s -C "$fixture/repo" release-validate-pin
fail 'signing subkey' env STRUCTCORPUS_PGP_KEY_ID="$wrong_subkey" make --no-print-directory -s -C "$fixture/repo" release-validate-pin
fail 'invalid configured' env STRUCTCORPUS_PGP_KEY_ID="${selector%!}" make --no-print-directory -s -C "$fixture/repo" release-validate-pin

# Anchors: generated once from the pin, never overwritten.
run release-insert-anchors >"$fixture/output"
[[ "$(cat "$anchors")" == "gpg $primary" ]] || {
  echo 'error: generated anchors differ from the documented derivation' >&2
  exit 1
}
[[ -s "$anchors_ndjson" ]]
"$fixture/repo/scripts/validate-release-anchors.sh" >/dev/null
cp "$anchors" "$fixture/anchors-copy"
cp "$anchors_ndjson" "$fixture/anchors-ndjson-copy"
fail 'fingerprint anchors already exist' make --no-print-directory -s -C "$fixture/repo" release-insert-anchors
cmp "$anchors" "$fixture/anchors-copy"
cmp "$anchors_ndjson" "$fixture/anchors-ndjson-copy"
printf 'gpg %s\n' "$wrong_primary" >"$anchors"
fail 'primary pin differs' "$fixture/repo/scripts/validate-release-anchors.sh"
printf 'gpg %s\n' "$(tr 'A-F' 'a-f' <<<"$primary")" >"$anchors"
fail 'exactly one gpg line' "$fixture/repo/scripts/validate-release-anchors.sh"
printf 'gpg %s\nextra\n' "$primary" >"$anchors"
fail 'exactly one gpg line' "$fixture/repo/scripts/validate-release-anchors.sh"
printf 'gpg %s' "$primary" >"$anchors"
fail 'exactly one gpg line' "$fixture/repo/scripts/validate-release-anchors.sh"
cp "$fixture/anchors-copy" "$anchors"
"$fixture/repo/scripts/validate-release-anchors.sh" >/dev/null
rm "$anchors" "$anchors_ndjson"

gpg --homedir "$fixture/home" --batch --armor --export-secret-keys "$selector" >"$pin"
fail 'private material in gpg' run release-validate-pin
fail 'private material in gpg' "$fixture/repo/scripts/release-insert-anchors.sh"
[[ ! -e "$anchors" ]]
cp "$fixture/pin-copy" "$pin"
gpg --homedir "$fixture/home" --batch --armor --export-secret-keys "$selector" >"$fixture/repo/docs/security/unexpected.asc"
fail 'public pin scan failed' run release-validate-pin
rm "$fixture/repo/docs/security/unexpected.asc"
gpg --homedir "$fixture/home" --batch --pinentry-mode loopback --passphrase '' \
  --quick-gen-key 'Synthetic extra <extra@example.invalid>' ed25519 cert 1d >/dev/null 2>&1
extra="$(gpg --homedir "$fixture/home" --batch --with-colons --fingerprint --list-keys 'Synthetic extra' | awk -F: '$1 == "fpr" { print $10; exit }')"
gpg --homedir "$fixture/home" --batch --armor --export "$extra" >>"$pin"
fail 'exactly one public primary' run release-validate-pin
fail 'exactly one public primary' "$fixture/repo/scripts/release-insert-anchors.sh"
cp "$fixture/pin-copy" "$pin"
rm "$pin"
fail 'default GPG home' env HOME="$fixture/other-home" STRUCTCORPUS_GPG_HOMEDIR="$fixture/other-home/.gnupg" make --no-print-directory -s -C "$fixture/repo" release-export-pin
ln -s "$fixture/pin-copy" "$pin"
fail 'public pin already exists' run release-export-pin
fail 'public GPG pin' run release-validate-pin
echo '[ok] Synthetic pin export, anchor derivation, no-overwrite and precursor guards passed'
