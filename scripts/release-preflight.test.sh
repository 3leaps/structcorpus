#!/usr/bin/env bash
# Drive release-preflight.sh through every gate to its terminal `make check`
# call, with that final gate passing and failing. python3 unittest, goneat and make are test
# doubles; the repository, origin and clone-outside-$HOME steps are real.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
unset RELEASE_TAG STRUCTCORPUS_RELEASE_TAG

repo="$scratch/repo"
mkdir -p "$repo/scripts" "$repo/config/release" "$repo/docs/security" "$repo/keys" "$scratch/bin"
cp "$root/scripts/release-preflight.sh" "$root/scripts/release-guard-release-surfaces.sh" \
  "$root/scripts/release-github-preflight.sh" "$root/scripts/release-gh.sh" \
  "$root/scripts/release-verify-committed-anchors.sh" "$root/scripts/release-decernor.sh" \
  "$root/scripts/validate-release-anchors.sh" "$root/scripts/committed_tree.py" \
  "$root/scripts/export-committed-tree.py" "$root/scripts/content-check.py" \
  "$root/scripts/surface-canary.py" \
  "$root/scripts/surface-catalog-path.py" "$root/scripts/surface-scan.sh" "$repo/scripts/"
cp "$root/docs/security/release-signing-keys.asc" "$repo/docs/security/"
cp "$root/keys/expected-fingerprints.txt" "$root/keys/expected-fingerprints.ndjson" "$repo/keys/"
if [[ -z "${STRUCTCORPUS_DECERNOR_BIN:-}" ]]; then
  if [[ "${CI:-}" == "true" ]]; then
    echo 'error: STRUCTCORPUS_DECERNOR_BIN required in CI' >&2
    exit 1
  fi
  STRUCTCORPUS_DECERNOR_BIN="$(command -v decernor)" || {
    echo 'error: STRUCTCORPUS_DECERNOR_BIN required (absolute path to decernor >= 0.1.8)' >&2
    exit 1
  }
  export STRUCTCORPUS_DECERNOR_BIN
fi
printf '1.2.3\n' >"$repo/VERSION"
good_changelog() {
  cat <<'MD'
# Changelog

## [Unreleased]

## [1.2.3] - 2026-10-13

- A record.

[Unreleased]: https://github.com/3leaps/structcorpus/compare/v1.2.3...HEAD
[1.2.3]: https://github.com/3leaps/structcorpus/compare/v1.2.2...v1.2.3
MD
}
good_changelog >"$repo/CHANGELOG.md"
git init -q -b main "$repo"
git -C "$repo" -c user.name=fixture -c user.email=fixture@example.invalid add -A
git -C "$repo" -c user.name=fixture -c user.email=fixture@example.invalid commit -qm fixture
git init -q --bare -b main "$scratch/origin.git"
git -C "$repo" remote add origin "$scratch/origin.git"
git -C "$repo" push -q origin main

# Test doubles: record calls; make honors FIXTURE_CHECK.
real_python3="$(command -v python3)"
cat >"$scratch/bin/python3" <<SH
#!/usr/bin/env bash
case " \$* " in
    *" -m unittest "*) printf 'python3 %s\\n' "\$*" >> "\$FIXTURE_LOG" ;;
    *) exec "$real_python3" "\$@" ;;
esac
SH
cat >"$scratch/bin/goneat" <<'SH'
#!/usr/bin/env bash
printf 'goneat %s\n' "$*" >> "$FIXTURE_LOG"
SH
cat >"$scratch/bin/make" <<'SH'
#!/usr/bin/env bash
printf 'make %s\n' "$*" >> "$FIXTURE_LOG"
[[ "$*" == "--no-print-directory check" ]] || exit 3
[[ "${FIXTURE_CHECK:-pass}" == pass ]]
SH
cat >"$scratch/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "${FIXTURE_GH_PREFLIGHT:-pass}" == pass ]] || exit 1
case "${2:-}" in
repos/3leaps/structcorpus/rulesets\?per_page=100)
    printf '[{"id":24954486,"name":"Tag Publish Protection","target":"tag","source_type":"Repository","source":"3leaps/structcorpus","enforcement":"active"}]\n'
    ;;
repos/3leaps/structcorpus/rulesets/24954486)
    printf '{"id":24954486,"name":"Tag Publish Protection","target":"tag","source_type":"Repository","source":"3leaps/structcorpus","enforcement":"active","conditions":{"ref_name":{"exclude":[],"include":["refs/tags/v*"]}},"rules":[{"type":"creation"},{"type":"update"},{"type":"deletion"},{"type":"non_fast_forward"}],"bypass_actors":[{"actor_id":null,"actor_type":"OrganizationAdmin","bypass_mode":"always"}]}\n'
    ;;
repos/3leaps/structcorpus/immutable-releases)
    printf '{"enabled":true}\n'
    ;;
*)
    exit 2
    ;;
esac
SH
chmod +x "$scratch/bin/"*
export PATH="$scratch/bin:$PATH" FIXTURE_LOG="$scratch/calls.log"

run() {
  : >"$FIXTURE_LOG"
  (cd "$repo" && "$@" ./scripts/release-preflight.sh) >"$scratch/out" 2>&1
}

# Final gate passes: preflight completes and check was the terminal call.
run env FIXTURE_CHECK=pass || {
  cat "$scratch/out" >&2
  echo 'error: preflight failed with a passing final gate' >&2
  exit 1
}
grep -q '^\[ok\] check gate passed' "$scratch/out"
grep -q '^\[ok\] preflight passed for v1.2.3' "$scratch/out"
[[ "$(tail -1 "$FIXTURE_LOG")" == 'make --no-print-directory check' ]]
grep -q '^python3 -B -m unittest discover -s tests$' "$FIXTURE_LOG"

# Final gate fails: preflight fails, names the gate, and never claims success.
if run env FIXTURE_CHECK=fail; then
  echo 'error: preflight passed with a failing final gate' >&2
  exit 1
fi
grep -q 'make check failed' "$scratch/out"
if grep -q 'preflight passed' "$scratch/out"; then
  echo 'error: preflight claimed success after a failed final gate' >&2
  exit 1
fi

# Unset or relative STRUCTCORPUS_DECERNOR_BIN fails closed before later gates.
if run env -u STRUCTCORPUS_DECERNOR_BIN FIXTURE_CHECK=pass; then
  echo 'error: preflight passed without STRUCTCORPUS_DECERNOR_BIN' >&2
  exit 1
fi
grep -q 'committed release anchors check failed' "$scratch/out"
[[ "$(grep -c '^make' "$FIXTURE_LOG")" == 0 ]] || {
  echo 'error: check ran after committed anchors failure' >&2
  exit 1
}

# A dirty tree stops before any later gate runs.
printf 'x\n' >"$repo/untracked"
if run env FIXTURE_CHECK=pass; then
  echo 'error: preflight passed with a dirty tree' >&2
  exit 1
fi
grep -q 'working tree is not clean' "$scratch/out"
[[ ! -s "$FIXTURE_LOG" ]]
rm "$repo/untracked"

# The changelog must carry a dated section and compare links for this version.
changelog_case() { # reason changelog-content
  local reason="$1"
  printf '%s\n' "$2" >"$repo/CHANGELOG.md"
  git -C "$repo" -c user.name=fixture -c user.email=fixture@example.invalid commit -qam "changelog: $reason"
  git -C "$repo" push -q origin main
  if run env FIXTURE_CHECK=pass; then
    echo "error: preflight passed with changelog: $reason" >&2
    exit 1
  fi
  grep -qF -- "$reason" "$scratch/out" || {
    echo "error: missing named refusal: $reason" >&2
    cat "$scratch/out" >&2
    exit 1
  }
  [[ "$(grep -c '^make' "$FIXTURE_LOG")" == 0 ]] || {
    echo 'error: later gates ran after a changelog refusal' >&2
    exit 1
  }
}
good="$(good_changelog)"
changelog_case 'has no dated [1.2.3] heading' "${good//'## [1.2.3] - 2026-10-13'/'## [1.2.3]'}"
changelog_case 'has no dated [1.2.3] heading' "${good//'## [1.2.3]'/'## [1.2.4]'}"
changelog_case 'release surfaces do not match VERSION' "${good//v1.2.3...HEAD/v1.2.2...HEAD}"
changelog_case 'release surfaces do not match VERSION' "$(printf '%s\n' "$good" | sed '/^\[1\.2\.3\]: /d')"
# Restore the valid changelog: preflight passes again.
good_changelog >"$repo/CHANGELOG.md"
git -C "$repo" -c user.name=fixture -c user.email=fixture@example.invalid commit -qam 'changelog: restore'
git -C "$repo" push -q origin main
run env FIXTURE_CHECK=pass || {
  cat "$scratch/out" >&2
  echo 'error: preflight failed with a valid changelog' >&2
  exit 1
}
grep -q '^\[ok\] CHANGELOG.md section and compare links cover 1.2.3' "$scratch/out"

echo '[ok] preflight reaches its final gate and fails closed when it fails'
