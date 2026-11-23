#!/usr/bin/env bash
# release-fetch-decernor.test.sh - Offline controls for the checker download gate
#
# Runs the real scripts/release-fetch-decernor.sh in a throwaway repository with
# a stub curl that serves a local archive, and proves (PDR-0008 §2.5; EPR-0002):
# - a matching digest installs and resolves (positive control: the harness can pass)
# - wrong bytes are refused at the digest comparison, before extraction, and the
#   archive's binary is never executed
# - a failed download, an unpinned platform, a duplicated platform line and a
#   malformed digest are each refused for their own reason
#
# Needs no network, gpg, or real checker.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

failures=0
pass() { echo "[ok] $1"; }
fail() {
  echo "[!!] $1" >&2
  failures=$((failures + 1))
}

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# --- fixture repository ------------------------------------------------------
repo="$work/repo"
mkdir -p "$repo/scripts" "$repo/config/release"
cp "$root/scripts/release-fetch-decernor.sh" "$root/scripts/release-decernor.sh" "$repo/scripts/"
git -C "$repo" init --quiet

# A fake decernor that passes the identity checks and records any execution.
fake_decernor() {
  local dir="$1" marker="$2"
  mkdir -p "$dir"
  cat >"$dir/decernor" <<EOF
#!/usr/bin/env bash
echo ran >>"$marker"
case "\$*" in
  "version") echo "decernor 0.1.9" ;;
  "version -e") printf 'Version:         0.1.9\nCommit:          0000000\nBuild Date:      2026-01-01T00:00:00Z\nGo Version:      go1.0\nGofulmen:        v0.0.0\nCrucible:        v0.0.0\n' ;;
  *) exit 2 ;;
esac
EOF
  chmod 755 "$dir/decernor"
}

good_marker="$work/good-ran"
bad_marker="$work/bad-ran"
fake_decernor "$work/good" "$good_marker"
fake_decernor "$work/bad" "$bad_marker"
echo "tampered" >>"$work/bad/decernor"
tar -czf "$work/good.tar.gz" -C "$work/good" decernor
tar -czf "$work/bad.tar.gz" -C "$work/bad" decernor
good_digest="$(sha256 "$work/good.tar.gz")"
[[ "$good_digest" != "$(sha256 "$work/bad.tar.gz")" ]] || {
  echo "error: fixture archives must differ" >&2
  exit 1
}

# Stub curl: serve $STUB_ARCHIVE to --output and log the URL; STUB_FAIL=1 fails.
mkdir "$work/stub"
cat >"$work/stub/curl" <<'EOF'
#!/usr/bin/env bash
out="" url=""
while (($#)); do
    case "$1" in
        --output) out="$2"; shift 2 ;;
        https://*) url="$1"; shift ;;
        *) shift ;;
    esac
done
echo "$url" >>"$STUB_LOG"
[[ "${STUB_FAIL:-}" != 1 ]] || { echo "curl: (22) The requested URL returned error: 404" >&2; exit 22; }
cp "$STUB_ARCHIVE" "$out"
EOF
chmod 755 "$work/stub/curl"

pins() { printf '%s\n' "$@" >"$repo/config/release/decernor-ci-sha256.txt"; }

# Usage: fetch ARCHIVE [NAME=VALUE ...]; sets $rc, $dest; output in $work/out, $work/err.
fetch() {
  local archive="$1"
  shift
  dest="$(mktemp -d "$work/dest.XXXXXX")"
  : >"$work/curl.log"
  rc=0
  (cd "$repo" && env PATH="$work/stub:$PATH" STUB_LOG="$work/curl.log" STUB_ARCHIVE="$archive" "$@" \
    ./scripts/release-fetch-decernor.sh linux_amd64 "$dest") >"$work/out" 2>"$work/err" || rc=$?
}

expect_refused() {
  local label="$1" pattern="$2"
  if ((rc == 0)); then
    fail "$label: accepted"
  elif ! grep -q -- "$pattern" "$work/err"; then
    fail "$label: refused for the wrong reason: $(cat "$work/err")"
  elif [[ -e "$dest/decernor" ]]; then
    fail "$label: refused, but a binary was extracted"
  else
    pass "$label: refused"
  fi
}

# --- positive control ---------------------------------------------------------
pins "$good_digest  decernor_0.1.9_linux_amd64.tar.gz"
fetch "$work/good.tar.gz"
if ((rc != 0)); then
  fail "pinned archive: refused: $(cat "$work/err")"
elif [[ "$(cat "$work/out")" != "$dest/decernor" && "$(cat "$work/out")" != "$(cd "$dest" && pwd -P)/decernor" ]]; then
  fail "pinned archive: printed '$(cat "$work/out")'"
elif [[ ! -s "$good_marker" ]]; then
  fail "pinned archive: installed binary was not identity-checked"
else
  pass "pinned archive: installed and identity-checked"
fi
if grep -Fqx "https://github.com/3leaps/decernor/releases/download/v0.1.9/decernor_0.1.9_linux_amd64.tar.gz" \
  "$work/curl.log"; then
  pass "download URL derived from the pinned archive name"
else
  fail "download URL: $(cat "$work/curl.log")"
fi
[[ ! -e "$dest/decernor_0.1.9_linux_amd64.tar.gz" ]] || fail "pinned archive: archive left beside the binary"

# --- wrong bytes ----------------------------------------------------------------
fetch "$work/bad.tar.gz"
expect_refused "archive with wrong bytes" "does not match the pinned $good_digest"
if [[ -e "$bad_marker" ]]; then
  fail "archive with wrong bytes: its binary was executed"
else
  pass "archive with wrong bytes: binary never executed"
fi

# --- other refusals -------------------------------------------------------------
fetch "$work/good.tar.gz" STUB_FAIL=1
expect_refused "failed download" "404"

pins "$good_digest  decernor_0.1.9_darwin_arm64.tar.gz"
fetch "$work/good.tar.gz"
expect_refused "platform not pinned" "expected exactly one pinned archive for linux_amd64"

pins "$good_digest  decernor_0.1.9_linux_amd64.tar.gz" "$good_digest  decernor_0.1.9_linux_amd64.tar.gz"
fetch "$work/good.tar.gz"
expect_refused "platform pinned twice" "expected exactly one pinned archive for linux_amd64"

pins "${good_digest:0:63}  decernor_0.1.9_linux_amd64.tar.gz"
fetch "$work/good.tar.gz"
expect_refused "malformed digest" "malformed digest"

pins "$good_digest  decernor_latest_linux_amd64.tar.gz"
fetch "$work/good.tar.gz"
expect_refused "unversioned archive name" "malformed archive name"

if ((failures)); then
  echo "[!!] checker download controls: $failures failure(s)" >&2
  exit 1
fi
echo "[ok] checker download controls passed"
