#!/usr/bin/env bash
# Pre-tag gate: every check that would otherwise fail only after the signed tag
# is pushed. Read-only; run from the exact main commit that will be tagged.
#
# Usage: STRUCTCORPUS_RELEASE_TAG=vX.Y.Z release-preflight.sh   (no default is derived)
set -euo pipefail
for _git_var in $(compgen -e); do
  case "$_git_var" in
    GIT_COMMITTER_NAME | GIT_COMMITTER_EMAIL | GIT_AUTHOR_NAME | GIT_AUTHOR_EMAIL | GIT_CONFIG_NOSYSTEM) ;;
    GIT_*) unset "$_git_var" ;;
  esac
done
unset _git_var
export GIT_NO_REPLACE_OBJECTS=1
die() {
  echo "[!!] $*" >&2
  exit 1
}
ok() { echo "[ok] $*"; }
root="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$root"
# shellcheck source=scripts/release-guard-tag-input.sh
source "$root/scripts/release-guard-tag-input.sh"
release_guard_tag_input || exit 1
version="$(tr -d ' \t\r\n' <VERSION)"
tag="$STRUCTCORPUS_RELEASE_TAG"
[[ "$tag" == "v$version" ]] || die "release tag $tag does not match VERSION $version"

[[ -z "$(git status --porcelain)" ]] || die 'working tree is not clean'
ok 'working tree is clean'
git fetch --quiet --no-tags origin '+refs/heads/main:refs/remotes/origin/main' ||
  die 'could not fetch origin/main'
[[ "$(git rev-parse HEAD)" == "$(git rev-parse refs/remotes/origin/main)" ]] ||
  die 'HEAD is not origin/main; tag only the merged main commit'
ok "HEAD is origin/main ($(git rev-parse --short HEAD))"

grep -qE "^## \[$version\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$" CHANGELOG.md || die "CHANGELOG.md has no dated [$version] heading"
./scripts/release-guard-release-surfaces.sh >/dev/null ||
  die 'release surfaces do not match VERSION (run scripts/release-guard-release-surfaces.sh)'
ok "CHANGELOG.md section and compare links cover $version"

./scripts/release-verify-committed-anchors.sh >/dev/null ||
  die 'committed release anchors check failed (run scripts/release-verify-committed-anchors.sh)'
ok 'committed release anchors and public pin verified'
./scripts/release-github-preflight.sh >/dev/null ||
  die 'GitHub release preflight failed (run scripts/release-github-preflight.sh)'
ok 'GitHub ruleset and immutable releases verified'
python3 -I -B "$root/scripts/content-check.py" "$root" HEAD >/dev/null ||
  die 'content-check failed (run python3 -I -B scripts/content-check.py)'
if [[ -n "${LIMENSAFE_CATALOG_PATH+set}" ]]; then
  STRUCTCORPUS_SURFACE_SCOPE=release ./scripts/surface-scan.sh >/dev/null ||
    die 'public-surface hygiene check failed (run scripts/surface-scan.sh)'
  ok 'public-surface hygiene verified (content-check and limensafe catalog)'
else
  ok 'content-check verified (limensafe catalog not set; use make release-preflight for required catalog scan)'
fi
goneat assess --categories dates --fail-on high >/dev/null 2>&1 ||
  die 'dates check failed (run goneat assess --categories dates)'
ok 'dates are consistent with repository history'

# Tests must not depend on where the checkout lives (packagers build outside $HOME).
if [[ -d /private/tmp ]]; then
  outside="$(mktemp -d /private/tmp/structcorpus-preflight.XXXXXX)"
else
  outside="$(mktemp -d /tmp/structcorpus-preflight.XXXXXX)"
fi
trap 'rm -rf "$outside"' EXIT
outside_real="$(cd "$outside" && pwd -P)"
home_real="$(cd "$HOME" && pwd -P)"
[[ "$outside_real/" != "$home_real/"* ]] || die "temporary clone $outside_real is under the home directory"
git clone --quiet --no-hardlinks "$root" "$outside/src"
if ! (cd "$outside/src" && python3 -B scripts/run-unit-tests.py tests >"$outside/test.log" 2>&1); then
  tail -20 "$outside/test.log" >&2
  die 'tests fail from a clone outside the home directory'
fi
ok 'tests pass from a clone outside the home directory'

make --no-print-directory check >/dev/null || die 'make check failed'
ok 'check gate passed'
echo "[ok] preflight passed for $tag at $(git rev-parse --short HEAD); ready to tag"
