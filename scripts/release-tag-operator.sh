#!/usr/bin/env bash
# Maintainer entrypoint for message preparation, local signing and remote push.
set -euo pipefail

mode="${1:-}"
case "$mode" in
  prepare-message | local-tag | remote-push) ;;
  *)
    echo 'error: expected prepare-message, local-tag or remote-push' >&2
    exit 1
    ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
# Check the sole tag input, and refuse the generic alias, before an optional
# loader can use either to select a cut.
# shellcheck source=scripts/release-guard-tag-input.sh
source "$root/scripts/release-guard-tag-input.sh"
release_guard_tag_input || exit 1
[[ "$STRUCTCORPUS_RELEASE_TAG" == "v$(cat VERSION)" ]] || {
  echo 'error: release tag must match VERSION' >&2
  exit 1
}
export STRUCTCORPUS_RELEASE_TAG

if [[ "${STRUCTCORPUS_APPROVED_ENV_LOADER+set}" == set ]]; then
  loader="$STRUCTCORPUS_APPROVED_ENV_LOADER"
  [[ "$loader" == /* && -f "$loader" && -r "$loader" && ! -L "$loader" ]] || {
    echo 'error: approved external environment loader must be a readable absolute regular file' >&2
    exit 1
  }
  loader_dir="$(cd "$(dirname "$loader")" && pwd -P)"
  case "$loader_dir/" in "$root/" | "$root/"*)
    echo 'error: approved environment loader must be outside the repository' >&2
    exit 1
    ;;
  esac
  # The approved operator script may set shell options. Hide its output and
  # check its exit status before restoring strict mode for all later guards.
  # shellcheck disable=SC1090
  if source "$loader" >/dev/null 2>&1; then
    loader_ok=1
  else
    loader_ok=0
  fi
  set -euo pipefail
  [[ "$loader_ok" == 1 ]] || {
    echo 'error: approved environment loader failed' >&2
    exit 1
  }
  release_guard_tag_input || exit 1
fi

# A sourced environment may change directory. Bind every guard to this repo.
cd "$root" || {
  echo 'error: repository root unavailable' >&2
  exit 1
}
[[ "$(pwd -P)" == "$root" ]] || {
  echo 'error: repository root changed' >&2
  exit 1
}
[[ "${STRUCTCORPUS_RELEASE_TAG:-}" == "v$(cat VERSION)" ]] || {
  echo 'error: loaded release tag differs from VERSION' >&2
  exit 1
}
if [[ "$mode" == prepare-message ]]; then
  export STRUCTCORPUS_RELEASE_TAG STRUCTCORPUS_TAG_MESSAGE_DIR
  exec "$root/scripts/release-prepare-tag-message.py"
fi
export STRUCTCORPUS_RELEASE_TAG STRUCTCORPUS_TAG_MESSAGE_DIR \
  STRUCTCORPUS_TAGGER_NAME STRUCTCORPUS_TAGGER_EMAIL \
  STRUCTCORPUS_GPG_SIGNING_FINGERPRINT STRUCTCORPUS_PGP_KEY_ID \
  STRUCTCORPUS_GPG_HOMEDIR

# shellcheck source=scripts/release-tag-common.sh
source "$root/scripts/release-tag-common.sh"
tag_version
tag_identity
[[ "$(git symbolic-ref --quiet --short HEAD)" == main ]] || {
  echo 'error: release tag targets require main' >&2
  exit 1
}
tag_checkout
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
  echo 'error: clean checkout required' >&2
  exit 1
}
tag_key_selector
tag_expected_message >/dev/null
"$root/scripts/release-inspect-tag-ruleset.sh" "$STRUCTCORPUS_RELEASE_TAG"

case "$mode" in
  local-tag) "$root/scripts/release-tag.sh" ;;
  remote-push) "$root/scripts/release-push-tag.sh" ;;
esac
