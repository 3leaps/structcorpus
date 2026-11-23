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
  "$root/scripts/release-guard-tag-input.sh" \
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
    *"/run-unit-tests.py "* | *" scripts/run-unit-tests.py "*) printf 'python3 %s\\n' "\$*" >> "\$FIXTURE_LOG" ;;
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
  (cd "$repo" && env STRUCTCORPUS_RELEASE_TAG=v1.2.3 "$@" ./scripts/release-preflight.sh) >"$scratch/out" 2>&1
}
# run_untagged: no STRUCTCORPUS_RELEASE_TAG at all.
run_untagged() {
  : >"$FIXTURE_LOG"
  (cd "$repo" && env -u STRUCTCORPUS_RELEASE_TAG "$@" ./scripts/release-preflight.sh) >"$scratch/out" 2>&1
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
grep -q '^python3 -B scripts/run-unit-tests.py tests$' "$FIXTURE_LOG"

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

# The tag is an explicit input: no VERSION-derived default, and the generic
# alias is refused even when empty, before any other gate runs.
if run_untagged env FIXTURE_CHECK=pass; then
  echo 'error: preflight passed without STRUCTCORPUS_RELEASE_TAG' >&2
  exit 1
fi
grep -q 'STRUCTCORPUS_RELEASE_TAG is required' "$scratch/out"
[[ ! -s "$FIXTURE_LOG" ]] || {
  echo 'error: preflight ran a gate before refusing a missing tag' >&2
  exit 1
}
for alias in v1.2.3 ''; do
  if run env RELEASE_TAG="$alias" FIXTURE_CHECK=pass; then
    echo "error: preflight passed with RELEASE_TAG='$alias'" >&2
    exit 1
  fi
  grep -q 'generic RELEASE_TAG alias is forbidden' "$scratch/out"
done

# The unit-test gate itself, with real Python: it must refuse zero discovered
# tests (unittest alone exits 0 for that on Python 3.9 to 3.11), a failing test
# and an import error, and accept a passing test. Every python3 found is tried,
# so a machine carrying the 3.9 floor exercises it.
runner="$root/scripts/run-unit-tests.py"
pythons=()
for candidate in "$(PATH="${PATH#"$scratch/bin:"}" command -v python3)" /usr/bin/python3; do
  [[ -x "$candidate" ]] || continue
  for seen in ${pythons[@]+"${pythons[@]}"}; do [[ "$seen" -ef "$candidate" ]] && continue 2; done
  pythons+=("$candidate")
done
[[ "${#pythons[@]}" -gt 0 ]] || {
  echo 'error: no python3 for the unit-test gate controls' >&2
  exit 1
}
for case in pass zero fail importerr skipped mixed subskip classskip modskip onlyclassskip subfail setupsub bodysub cleanupsub usucc xfail; do mkdir -p "$scratch/ut/$case/tests"; done
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n' >"$scratch/ut/pass/tests/test_a.py"
printf '# no tests\n' >"$scratch/ut/zero/tests/test_empty.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.fail("x")\n' >"$scratch/ut/fail/tests/test_a.py"
printf 'import not_a_module_for_this_control\n' >"$scratch/ut/importerr/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    @unittest.skip("x")\n    def test_skip(self):\n        pass\n' >"$scratch/ut/skipped/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n\n    @unittest.skip("x")\n    def test_skip(self):\n        pass\n' >"$scratch/ut/mixed/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n\n    def test_sub(self):\n        with self.subTest(i=1):\n            self.skipTest("x")\n' >"$scratch/ut/subskip/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n\n\nclass S(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        raise unittest.SkipTest("x")\n\n    def test_never(self):\n        pass\n' >"$scratch/ut/classskip/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n' >"$scratch/ut/modskip/tests/test_a.py"
printf 'import unittest\n\n\ndef setUpModule():\n    raise unittest.SkipTest("x")\n\n\nclass S(unittest.TestCase):\n    def test_never(self):\n        pass\n' >"$scratch/ut/modskip/tests/test_b.py"
printf 'import unittest\n\n\nclass S(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        raise unittest.SkipTest("x")\n\n    def test_never(self):\n        pass\n' >"$scratch/ut/onlyclassskip/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_sub(self):\n        with self.subTest(i=1):\n            self.fail("x")\n' >"$scratch/ut/subfail/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def setUp(self):\n        with self.subTest(i=1):\n            pass\n        self.skipTest("x")\n\n    def test_never(self):\n        pass\n' >"$scratch/ut/setupsub/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        with self.subTest(i=1):\n            pass\n        self.skipTest("x")\n' >"$scratch/ut/bodysub/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def setUp(self):\n        def c():\n            with self.subTest(i=2):\n                pass\n\n        self.addCleanup(c)\n        self.skipTest("x")\n\n    def test_never(self):\n        pass\n' >"$scratch/ut/cleanupsub/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_x(self):\n        pass\n' >"$scratch/ut/usucc/tests/test_a.py"
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_x(self):\n        self.fail("x")\n' >"$scratch/ut/xfail/tests/test_a.py"
for py in "${pythons[@]}"; do
  version="$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  for case in pass zero fail importerr skipped mixed subskip classskip modskip onlyclassskip subfail setupsub bodysub cleanupsub usucc xfail; do
    rc=0
    (cd "$scratch/ut/$case" && "$py" -B "$runner" tests) >/dev/null 2>&1 || rc=$?
    want=1
    case "$case" in pass | mixed | subskip | classskip | modskip | xfail) want=0 ;; esac
    [[ "$rc" == "$want" ]] || {
      echo "error: unit-test gate on Python $version: $case exited $rc, expected $want" >&2
      exit 1
    }
  done
  echo "[ok] unit-test gate on Python $version: accepts a pass with method, subtest, class or module skips and an expected failure; refuses zero tests, all or class-only skipped, a skipped test whose setUp, cleanup or body ran a subtest, a failure, a failing subtest, an unexpected success and an import error"
done

echo '[ok] preflight reaches its final gate and fails closed when it fails'
