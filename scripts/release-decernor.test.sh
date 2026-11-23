#!/usr/bin/env bash
# Synthetic public exports only; no operator keyring or maintainer key material.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
fixture="$(mktemp -d)"
cleanup() {
  local home
  for home in "$fixture/home" "$fixture/other-home"; do
    [[ -d "$home" ]] && gpgconf --homedir "$home" --kill all >/dev/null 2>&1 || true
  done
  rm -rf "$fixture"
}
trap cleanup EXIT
mkdir -p "$fixture/repo/scripts" "$fixture/repo/docs/security" "$fixture/repo/config/release" "$fixture/repo/keys" "$fixture/home" "$fixture/other-home"
chmod 700 "$fixture/home" "$fixture/other-home"
cp "$root/scripts/"{release-decernor.sh,release-insert-anchors.sh,install-release-anchors.sh,release-verify-committed-anchors.sh,validate-release-anchors.sh} "$fixture/repo/scripts/"
cp "$root/config/release/fingerprint-record.v0.schema.json" "$fixture/repo/config/release/"
bin="${STRUCTCORPUS_DECERNOR_BIN:-$(command -v decernor)}"
[[ "$bin" == /* ]]
fail() {
  if "$@" >"$fixture/output" 2>&1; then
    echo "error: expected rejection: $*" >&2
    exit 1
  fi
}
gpg --homedir "$fixture/home" --batch --pinentry-mode loopback --passphrase '' \
  --quick-gen-key 'Synthetic release <synthetic@example.invalid>' ed25519 sign 1d >/dev/null 2>&1
gpg --homedir "$fixture/home" --batch --armor --export >"$fixture/repo/docs/security/release-signing-keys.asc"
export STRUCTCORPUS_DECERNOR_BIN="$bin"
(
  # General resolver precedence is distinct from ceremony's explicit binding.
  source "$root/scripts/release-decernor.sh"
  resolve_release_decernor general
  [[ "$RELEASE_DECERNOR_BIN" == "$bin" ]]
  unset STRUCTCORPUS_DECERNOR_BIN
  DECERNOR_BIN="$bin" resolve_release_decernor general
  [[ "$RELEASE_DECERNOR_BIN" == "$bin" ]]
  unset DECERNOR_BIN
  mkdir -p "$fixture/path"
  cp "$bin" "$fixture/path/decernor"
  PATH="$fixture/path:$PATH"
  resolve_release_decernor general
  [[ "$RELEASE_DECERNOR_BIN" == "$fixture/path/decernor" ]]
)
"$fixture/repo/scripts/release-insert-anchors.sh" >/dev/null
"$fixture/repo/scripts/release-verify-committed-anchors.sh" >/dev/null

fail env -u STRUCTCORPUS_DECERNOR_BIN DECERNOR_BIN="$bin" "$fixture/repo/scripts/release-verify-committed-anchors.sh"
fail env -u STRUCTCORPUS_DECERNOR_BIN DECERNOR_BIN="$bin" "$fixture/repo/scripts/release-insert-anchors.sh"
fail env STRUCTCORPUS_DECERNOR_BIN=decernor "$fixture/repo/scripts/release-verify-committed-anchors.sh"
fail env STRUCTCORPUS_DECERNOR_BIN="$fixture/missing" "$fixture/repo/scripts/release-verify-committed-anchors.sh"
ln -s "$bin" "$fixture/symlink-decernor"
fail env STRUCTCORPUS_DECERNOR_BIN="$fixture/symlink-decernor" "$fixture/repo/scripts/release-verify-committed-anchors.sh"
cat >"$fixture/false-version" <<'EOF'
#!/usr/bin/env bash
case "$1 ${2:-}" in
  'version ') echo 'decernor 0.1.8' ;;
  'version -e') printf 'Version:         0.1.7\nCommit:          fake\nBuild Date:      fake\nGo Version:      fake\nGofulmen:        fake\nCrucible:        fake\n' ;;
esac
EOF
chmod +x "$fixture/false-version"
fail env STRUCTCORPUS_DECERNOR_BIN="$fixture/false-version" "$fixture/repo/scripts/release-verify-committed-anchors.sh"
sed 's/0\.1\.8/0.1.7/' "$fixture/false-version" >"$fixture/old-version"
chmod +x "$fixture/old-version"
fail env STRUCTCORPUS_DECERNOR_BIN="$fixture/old-version" "$fixture/repo/scripts/release-verify-committed-anchors.sh"
sed 's/decernor 0.1.8/other 0.1.8/' "$fixture/false-version" >"$fixture/wrong-identity"
chmod +x "$fixture/wrong-identity"
fail env STRUCTCORPUS_DECERNOR_BIN="$fixture/wrong-identity" "$fixture/repo/scripts/release-verify-committed-anchors.sh"
cp "$fixture/repo/keys/expected-fingerprints.txt" "$fixture/good.txt"
sed 's/^gpg ./gpg Z/' "$fixture/good.txt" >"$fixture/repo/keys/expected-fingerprints.txt"
fail "$fixture/repo/scripts/release-verify-committed-anchors.sh"
cp "$fixture/good.txt" "$fixture/repo/keys/expected-fingerprints.txt"
cp "$fixture/repo/keys/expected-fingerprints.ndjson" "$fixture/good.ndjson"
printf '\n' >>"$fixture/repo/keys/expected-fingerprints.ndjson"
fail "$fixture/repo/scripts/release-verify-committed-anchors.sh"
cp "$fixture/good.ndjson" "$fixture/repo/keys/expected-fingerprints.ndjson"
cp "$fixture/repo/docs/security/release-signing-keys.asc" "$fixture/primary.asc"
gpg --homedir "$fixture/other-home" --batch --pinentry-mode loopback --passphrase '' \
  --quick-gen-key 'Other synthetic <other@example.invalid>' ed25519 sign 1d >/dev/null 2>&1
gpg --homedir "$fixture/other-home" --batch --armor --export >"$fixture/repo/docs/security/release-signing-keys.asc"
fail "$fixture/repo/scripts/release-verify-committed-anchors.sh"
gpg --homedir "$fixture/home" --batch --import "$fixture/repo/docs/security/release-signing-keys.asc" >/dev/null 2>&1
gpg --homedir "$fixture/home" --batch --armor --export >"$fixture/repo/docs/security/release-signing-keys.asc"
fail "$fixture/repo/scripts/release-verify-committed-anchors.sh"
truncate -s 0 "$fixture/repo/docs/security/release-signing-keys.asc"
fail "$fixture/repo/scripts/release-verify-committed-anchors.sh"
cp "$fixture/primary.asc" "$fixture/repo/docs/security/release-signing-keys.asc"

# Existing anchors must not be overwritten. A verifier failure on a first
# write must leave dest empty (rollback), not a partial pair.
cp "$fixture/repo/keys/expected-fingerprints.txt" "$fixture/old.txt"
cp "$fixture/repo/keys/expected-fingerprints.ndjson" "$fixture/old.ndjson"
gpg --homedir "$fixture/other-home" --batch --armor --export >"$fixture/repo/docs/security/release-signing-keys.asc"
fail "$fixture/repo/scripts/release-insert-anchors.sh"
grep -q 'fingerprint anchors already exist' "$fixture/output"
cmp "$fixture/old.txt" "$fixture/repo/keys/expected-fingerprints.txt"
cmp "$fixture/old.ndjson" "$fixture/repo/keys/expected-fingerprints.ndjson"
cp "$fixture/primary.asc" "$fixture/repo/docs/security/release-signing-keys.asc"
# The third fingerprint derivation is the post-install verification.
cat >"$fixture/reject-verify" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == fingerprint ]]; then
    count="\$(cat "$fixture/fingerprint-count" 2> /dev/null || echo 0)"
    echo "\$((count + 1))" > "$fixture/fingerprint-count"
    [[ "\$count" -lt 2 ]] || exit 1
fi
exec "$bin" "\$@"
EOF
chmod +x "$fixture/reject-verify"
rm -f "$fixture/repo/keys/expected-fingerprints.txt" "$fixture/repo/keys/expected-fingerprints.ndjson"
fail env STRUCTCORPUS_DECERNOR_BIN="$fixture/reject-verify" "$fixture/repo/scripts/release-insert-anchors.sh"
[[ "$(cat "$fixture/fingerprint-count")" == 3 ]] || {
  echo 'error: the post-install verification did not run' >&2
  exit 1
}
[[ ! -e "$fixture/repo/keys/expected-fingerprints.txt" && ! -e "$fixture/repo/keys/expected-fingerprints.ndjson" ]]
mkdir -p "$fixture/stage"
cp "$fixture/old.txt" "$fixture/stage/expected-fingerprints.txt"
cp "$fixture/old.ndjson" "$fixture/stage/expected-fingerprints.ndjson"
fail "$fixture/repo/scripts/install-release-anchors.sh" "$fixture/stage" "$fixture/new-keys" false
[[ ! -e "$fixture/new-keys/expected-fingerprints.txt" && ! -e "$fixture/new-keys/expected-fingerprints.ndjson" ]]
echo '[ok] Decernor ceremony identity, export verification, and no-overwrite controls passed'
