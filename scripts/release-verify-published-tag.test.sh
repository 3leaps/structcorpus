#!/usr/bin/env bash
# Synthetic controls for the published-tag gate; all keys and remotes are temporary.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
bin="${STRUCTCORPUS_DECERNOR_BIN:-$(command -v decernor || true)}"
[[ -n "$bin" && -x "$bin" && "$bin" == /* ]] || {
  echo 'error: STRUCTCORPUS_DECERNOR_BIN required (absolute path to decernor >= 0.1.8)' >&2
  exit 1
}
export STRUCTCORPUS_DECERNOR_BIN="$bin"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
cleanup() {
  local home
  for home in "$scratch/gpg" "$scratch/attacker"; do
    [[ -d "$home" ]] && gpgconf --homedir "$home" --kill all >/dev/null 2>&1 || true
  done
  rm -rf "$scratch"
}
trap cleanup EXIT
export GNUPGHOME="$scratch/gpg"
mkdir -m 700 "$GNUPGHOME"
gpg --batch --pinentry-mode loopback --passphrase '' --quick-generate-key \
  '3 Leaps Infosec Team <infosec@3leaps.net>' ed25519 cert 0 >/dev/null 2>&1
primary="$(gpg --batch --with-colons --fingerprint --list-keys | awk -F: '$1=="fpr" {print $10;exit}')"
gpg --batch --pinentry-mode loopback --passphrase '' --quick-add-key "$primary" ed25519 sign 1d >/dev/null 2>&1
subkey="$(gpg --batch --with-colons --with-subkey-fingerprint --list-keys "$primary" | awk -F: '$1=="sub" {s=1;next} s && $1=="fpr" {print $10;exit}')"

git init -q --bare -b main "$scratch/remote.git"
src="$scratch/source"
git init -q -b main "$src"
git -C "$src" config user.name '3 Leaps Infosec Team'
git -C "$src" config user.email infosec@3leaps.net
git -C "$src" config gpg.format openpgp
git -C "$src" config gpg.program gpg
git -C "$src" config commit.gpgsign false
mkdir -p "$src/scripts" "$src/docs/security" "$src/keys" "$src/config/release"
cp "$root/scripts/"{verify-pinned-tag.sh,validate-release-anchors.sh,release-verify-published-tag.sh,release-decernor.sh,release-gh.sh,release-guard-tag-input.sh} "$src/scripts/"
cp "$root/config/release/tagger-identity.txt" "$src/config/release/"
printf '%s\n' "$subkey" >"$src/config/release/signing-subkey.txt"
gpg --batch --armor --export "$primary" >"$src/docs/security/release-signing-keys.asc"
"$bin" fingerprint "$src/docs/security/release-signing-keys.asc" --class public --kind gpg \
  --format ndjson --path-mode none --gpg-role primary >"$scratch/gpg.ndjson"
python3 - "$scratch" "$src/keys" <<'PY'
import json, pathlib, sys
base, keys = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
g = [json.loads(line) for line in (base / 'gpg.ndjson').read_text().splitlines() if line]
if len(g) != 1:
    raise SystemExit('error: expected one GPG primary')
(keys / 'expected-fingerprints.ndjson').write_text(json.dumps(g[0], separators=(',', ':')) + '\n')
(keys / 'expected-fingerprints.txt').write_text('gpg ' + g[0]['fingerprint'] + '\n')
PY
git -C "$src" add -A
git -C "$src" commit -qm fixture
commit="$(git -C "$src" rev-parse HEAD)"
sign_tag() {
  printf '%s\n' "$1" >"$scratch/msg"
  GIT_COMMITTER_NAME='3 Leaps Infosec Team' GIT_COMMITTER_EMAIL=infosec@3leaps.net \
    git -C "$src" -c gpg.format=openpgp -c gpg.program=gpg -c gpg.openpgp.program=gpg tag -fs -a --cleanup=verbatim \
    -u "$subkey!" -F "$scratch/msg" v1.2.3 >/dev/null
}
sign_tag 'Fixture release'
git -C "$src" remote add origin "$scratch/remote.git"
git -C "$src" push -q origin main refs/tags/v1.2.3

# The operator checkout is on a later main: the gate must not depend on it.
op="$scratch/operator"
git clone -q "$scratch/remote.git" "$op"
git -C "$op" config user.name 'Fixture Operator'
git -C "$op" config user.email operator@example.invalid
printf 'later\n' >"$op/later"
git -C "$op" add later
git -C "$op" commit -qm 'later main'
git -C "$op" remote set-url origin https://github.com/3leaps/structcorpus.git
git -C "$op" config url."$scratch/remote.git".insteadOf https://github.com/3leaps/structcorpus.git

# Stub gh: answer the git-data API from the fixture remote.
mkdir -p "$scratch/bin"
ln -s "$root/scripts/testdata/fake-gh-api.sh" "$scratch/bin/gh"
export PATH="$scratch/bin:$PATH" FIXTURE_REMOTE="$scratch/remote.git" STRUCTCORPUS_RELEASE_TAG=v1.2.3
export STRUCTCORPUS_GPG_SIGNING_FINGERPRINT="$primary"

# The operator's trusted checkout carries the current verifier and helpers.
cp "$root/scripts/"{verify-pinned-tag.sh,validate-release-anchors.sh,release-verify-published-tag.sh,release-decernor.sh,release-gh.sh,release-guard-tag-input.sh} "$op/scripts/"
gate() { (cd "$op" && ./scripts/release-verify-published-tag.sh); }
expect_fail() {
  if gate >"$scratch/out" 2>&1; then
    echo "error: expected rejection: $1" >&2
    exit 1
  fi
  grep -q "$1" "$scratch/out" || {
    echo "error: missing named rejection: $1" >&2
    cat "$scratch/out" >&2
    exit 1
  }
}
gate >/dev/null
# The temporary verification worktree is always removed.
[[ "$(git -C "$op" worktree list --porcelain | grep -c '^worktree ')" == 1 ]] || {
  echo 'error: verification worktree left behind' >&2
  exit 1
}

FIXTURE_GH_VERIFIED=false expect_fail 'GitHub does not report'

# Same commit, different (unsigned) annotated object: must fail.
GIT_COMMITTER_NAME='3 Leaps Infosec Team' GIT_COMMITTER_EMAIL=infosec@3leaps.net \
  git -C "$src" tag -fa -m 'Replacement' v1.2.3 "$commit"
git -C "$src" push -q --force origin refs/tags/v1.2.3
expect_fail 'does not verify against the pin'

# Lightweight replacement: must fail. The ref API reports a commit, not a tag
# object, so the lookup refuses before any local ref changes.
git -C "$scratch/remote.git" update-ref refs/tags/v1.2.3 "$commit"
expect_fail 'annotated tag required'

# Restore a valid signed tag: passes again.
sign_tag 'Fixture release'
git -C "$src" push -q --force origin refs/tags/v1.2.3
gate >/dev/null

# The approved primary must come from the maintainer environment.
(
  unset STRUCTCORPUS_GPG_SIGNING_FINGERPRINT
  expect_fail 'approved primary'
)
STRUCTCORPUS_GPG_SIGNING_FINGERPRINT="$(printf '%040d' 0)" expect_fail 'not the approved primary'

# An attacker commit carrying its own key and a matching fingerprint file is
# internally consistent but not approved, so it is rejected.
export GNUPGHOME="$scratch/attacker"
mkdir -m 700 "$GNUPGHOME"
gpg --batch --pinentry-mode loopback --passphrase '' --quick-generate-key \
  '3 Leaps Infosec Team <infosec@3leaps.net>' ed25519 cert 0 >/dev/null 2>&1
attacker="$(gpg --batch --with-colons --fingerprint --list-keys | awk -F: '$1=="fpr" {print $10;exit}')"
gpg --batch --pinentry-mode loopback --passphrase '' --quick-add-key "$attacker" ed25519 sign 1d >/dev/null 2>&1
attacker_sub="$(gpg --batch --with-colons --with-subkey-fingerprint --list-keys "$attacker" | awk -F: '$1=="sub" {s=1;next} s && $1=="fpr" {print $10;exit}')"
gpg --batch --armor --export "$attacker" >"$src/docs/security/release-signing-keys.asc"
"$bin" fingerprint "$src/docs/security/release-signing-keys.asc" --class public --kind gpg \
  --format ndjson --path-mode none --gpg-role primary >"$scratch/gpg.ndjson"
python3 - "$scratch" "$src/keys" <<'PY'
import json, pathlib, sys
base, keys = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
g = [json.loads(line) for line in (base / 'gpg.ndjson').read_text().splitlines() if line]
(keys / 'expected-fingerprints.ndjson').write_text(json.dumps(g[0], separators=(',', ':')) + '\n')
(keys / 'expected-fingerprints.txt').write_text('gpg ' + g[0]['fingerprint'] + '\n')
PY
git -C "$src" add -A
git -C "$src" commit -qm 'attacker pin'
printf 'Fixture release\n' >"$scratch/msg"
GIT_COMMITTER_NAME='3 Leaps Infosec Team' GIT_COMMITTER_EMAIL=infosec@3leaps.net \
  git -C "$src" -c gpg.format=openpgp -c gpg.program=gpg -c gpg.openpgp.program=gpg tag -fs -a --cleanup=verbatim \
  -u "$attacker_sub!" -F "$scratch/msg" v1.2.3 >/dev/null
git -C "$src" push -q origin main
git -C "$src" push -q --force origin refs/tags/v1.2.3
expect_fail 'not the approved primary'
gpgconf --homedir "$GNUPGHOME" --kill all >/dev/null 2>&1 || true
export GNUPGHOME="$scratch/gpg"
git -C "$src" reset -q --hard "$commit"
sign_tag 'Fixture release'
git -C "$src" push -q --force origin main refs/tags/v1.2.3
gate >/dev/null

# An unverified target carrying a marker-writing fake verifier and helper must
# never be executed: the gate runs only the operator's trusted scripts.
marker="$scratch/target-code-executed"
for script in verify-pinned-tag.sh validate-release-anchors.sh release-verify-published-tag.sh release-decernor.sh; do
  printf '#!/usr/bin/env bash\ntouch %q\nexit 0\n' "$marker" >"$src/scripts/$script"
  chmod +x "$src/scripts/$script"
done
git -C "$src" add -A
git -C "$src" commit -qm 'unverified target with fake verifier'
GIT_COMMITTER_NAME='3 Leaps Infosec Team' GIT_COMMITTER_EMAIL=infosec@3leaps.net \
  git -C "$src" tag -fa -m 'Unsigned replacement' v1.2.3
git -C "$src" push -q origin main
git -C "$src" push -q --force origin refs/tags/v1.2.3
expect_fail 'does not verify against the pin'
[[ ! -e "$marker" ]] || {
  echo 'error: code from the unverified tag target was executed' >&2
  exit 1
}
# Even a correctly signed target cannot run its own scripts in the gate.
sign_tag 'Fixture release'
git -C "$src" push -q --force origin refs/tags/v1.2.3
gate >/dev/null
[[ ! -e "$marker" ]] || {
  echo 'error: code from the tag target was executed' >&2
  exit 1
}

# Absent remote tag: must fail.
git -C "$scratch/remote.git" update-ref -d refs/tags/v1.2.3
expect_fail 'remote release tag is absent'
echo '[ok] published-tag gate controls passed'
