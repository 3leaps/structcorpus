#!/usr/bin/env bash
# Offline controls for scripts/release-ci-verify-tag.sh: the CI tag check is
# bound to the triggering event (commit and pushed tag object), refuses a tag
# that is lightweight, moved, replaced or different on GitHub at bind time,
# refuses movement after binding and during verification, and requires the
# pinned-tag verifier and GitHub's verdict for the bound object. The fake gh
# answers from a local bare origin; verify-pinned-tag.sh is a stub here (its
# own suite covers it).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
unset RELEASE_TAG STRUCTCORPUS_RELEASE_TAG
g() { git -c user.name=fixture -c user.email=fixture@example.invalid -c tag.gpgsign=false -c commit.gpgsign=false "$@"; }

origin="$scratch/origin.git"
src="$scratch/src"
g init -q -b main "$src"
g -C "$src" commit -q --allow-empty -m one
g -C "$src" commit -q --allow-empty -m two
c1="$(git -C "$src" rev-parse HEAD~1)"
c2="$(git -C "$src" rev-parse HEAD)"
g init -q --bare "$origin"
g -C "$src" push -q "$origin" main

work="$scratch/work"
reset_fixture() { # reset_fixture: annotated v1.2.3 on c1 in origin; fresh work clone at c1
  g -C "$src" tag -f -a -m 'Release 1.2.3' v1.2.3 "$c1" >/dev/null
  g -C "$src" push -q -f "$origin" refs/tags/v1.2.3
  rm -rf "$work"
  g clone -q --no-checkout "$origin" "$work"
  g -C "$work" -c advice.detachedHead=false checkout -q "$c1"
  mkdir -p "$work/scripts"
  cp "$root/scripts/release-ci-verify-tag.sh" "$root/scripts/release-gh.sh" "$work/scripts/"
  cat >"$work/scripts/verify-pinned-tag.sh" <<'STUB'
#!/usr/bin/env bash
echo "verify-pinned-tag $* tag=$STRUCTCORPUS_RELEASE_TAG" >>"$FIXTURE_LOG"
[[ -z "${FIXTURE_MOVE_DURING:-}" ]] || git -C "$FIXTURE_REMOTE" tag -f v1.2.3 "$FIXTURE_MOVE_DURING" >/dev/null
[[ "${FIXTURE_PIN:-pass}" == pass ]]
STUB
  chmod +x "$work/scripts/verify-pinned-tag.sh"
  object="$(git -C "$origin" rev-parse refs/tags/v1.2.3)"
}
mkdir -p "$scratch/bin"
ln -s "$root/scripts/testdata/fake-gh-api.sh" "$scratch/bin/gh"
export PATH="$scratch/bin:$PATH" FIXTURE_REMOTE="$origin" FIXTURE_LOG="$scratch/calls.log" GH_TOKEN=fixture
export GITHUB_REPOSITORY=3leaps/structcorpus TAG=v1.2.3 EVENT_REF=refs/tags/v1.2.3

ci() { # ci MODE [ENV...]
  local mode="$1"
  shift
  : >"$FIXTURE_LOG"
  (cd "$work" && env EVENT_SHA="$c1" EVENT_AFTER="${after:-$object}" "$@" ./scripts/release-ci-verify-tag.sh "$mode") >"$scratch/out" 2>&1
}
refused() { # refused PATTERN MODE [ENV...]
  local pattern="$1"
  shift
  if ci "$@"; then
    echo "error: accepted ($*)" >&2
    exit 1
  fi
  grep -q -- "$pattern" "$scratch/out" || {
    echo "error: refused for another reason than '$pattern' ($*)" >&2
    cat "$scratch/out" >&2
    exit 1
  }
}

# bind: positive control (the event names the pushed tag object).
reset_fixture
ci bind
[[ "$(cat "$scratch/out")" == "$object" ]]
# An event that names only the commit cannot bind the original object: refuse,
# both for the unchanged tag and after a same-commit replacement.
after="$c1" refused 'names only the commit' bind
# bind: refusals.
refused 'canonical' bind TAG=1.2.3
refused 'event ref is not this tag' bind EVENT_REF=refs/tags/v9.9.9
refused 'unexpected repository' bind GITHUB_REPOSITORY=other/repo
g -C "$work" -c advice.detachedHead=false checkout -q "$c2"
refused 'not the event commit' bind
reset_fixture
g -C "$src" tag -f v1.2.3 "$c1" >/dev/null # lightweight, same commit
g -C "$src" push -q -f "$origin" refs/tags/v1.2.3
refused 'not an annotated tag' bind
reset_fixture
old="$object"
g -C "$src" tag -f -a -m 'Release 1.2.3' v1.2.3 "$c2" >/dev/null # moved to another commit
g -C "$src" push -q -f "$origin" refs/tags/v1.2.3
after="$old" refused 'no longer points at the event commit' bind
reset_fixture
old="$object"
sleep 1
g -C "$src" tag -f -a -m 'Release 1.2.3 again' v1.2.3 "$c1" >/dev/null # replaced, same commit
g -C "$src" push -q -f "$origin" refs/tags/v1.2.3
after="$old" refused 'replaced after the triggering push' bind
after="$c1" refused 'names only the commit' bind
unset after

# verify: positive control, then each refusal.
reset_fixture
ci bind
ci verify TAG_OBJECT="$object"
grep -q '^verify-pinned-tag --published tag=v1.2.3$' "$FIXTURE_LOG"
refused 'bound tag object' verify TAG_OBJECT=
refused 'GitHub does not report' verify TAG_OBJECT="$object" FIXTURE_GH_VERIFIED=false
if ci verify TAG_OBJECT="$object" FIXTURE_PIN=fail; then
  echo 'error: accepted a failing pinned-tag verification' >&2
  exit 1
fi
g -C "$work" tag -f v1.2.3 "$c1" >/dev/null
refused 'local tag moved after binding' verify TAG_OBJECT="$object"
reset_fixture
ci bind
g -C "$src" tag -f -a -m 'Release 1.2.3 moved' v1.2.3 "$c1" >/dev/null
g -C "$src" push -q -f "$origin" refs/tags/v1.2.3
refused 'moved after binding' verify TAG_OBJECT="$object"
reset_fixture
ci bind
refused 'moved during verification' verify TAG_OBJECT="$object" FIXTURE_MOVE_DURING="$c2"

echo '[ok] CI tag verification is bound to the event tag object; refuses commit-only events and lightweight, moved, replaced and unverified tags'
