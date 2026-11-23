#!/usr/bin/env bash
# CI verification of a pushed version tag (PDR-0008 section 2.5), bound to the
# triggering event. A passing run is consistency evidence, not authorization.
#
#   bind    before the checker is installed: the event names the pushed tag
#           object, the fetched tag is that annotated object, it peels to the
#           event commit, the checkout is that commit, and the GitHub ref
#           agrees.
#           Prints the bound tag object id.
#   verify  after the checker is installed (STRUCTCORPUS_DECERNOR_BIN): the
#           bound object is still the local and remote tag, its signature and
#           the pin/anchors in the tagged commit verify, and GitHub reports
#           that object verified; the remote ref is re-read last.
#
# Inputs: TAG (github.ref_name), EVENT_REF (github.ref), EVENT_SHA (github.sha:
# the peeled commit, or the pushed tag object itself), EVENT_AFTER
# (github.event.after, which must be the pushed annotated tag object; a commit
# value is refused), GITHUB_REPOSITORY, GH_TOKEN; verify also needs TAG_OBJECT
# (the bind output).
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
  echo "error: $*" >&2
  exit 1
}
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
# shellcheck source=scripts/release-gh.sh
source "$root/scripts/release-gh.sh"
mode="${1:-}"
hex40='^[0-9a-f]{40}$'
[[ "${TAG:-}" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || die 'TAG must be a canonical vX.Y.Z tag'
[[ "${EVENT_REF:-}" == "refs/tags/$TAG" ]] || die 'the event ref is not this tag'
[[ "${EVENT_SHA:-}" =~ $hex40 ]] || die 'EVENT_SHA must be an object id'
[[ "${EVENT_AFTER:-}" =~ $hex40 ]] || die 'EVENT_AFTER must be an object id'
[[ "${GITHUB_REPOSITORY:-}" == 3leaps/structcorpus ]] || die 'unexpected repository'

remote_object() {
  local ref_json
  ref_json="$(release_gh api "repos/$GITHUB_REPOSITORY/git/ref/tags/$TAG")" || die 'the GitHub tag ref is unavailable'
  [[ "$(jq -r '.ref // empty' <<<"$ref_json")" == "refs/tags/$TAG" ]] || die 'GitHub returned another ref'
  [[ "$(jq -r '.object.type // empty' <<<"$ref_json")" == tag ]] || die "$TAG is not an annotated tag on GitHub"
  jq -r '.object.sha // empty' <<<"$ref_json"
}

# event_commit: the commit the event names. GitHub has been observed to report
# github.sha either as the peeled commit or as the annotated tag object itself;
# accept the tag object only when it is exactly the object `after` names.
event_commit() {
  case "$(git cat-file -t "$EVENT_SHA" 2>/dev/null || true)" in
    commit) printf '%s\n' "$EVENT_SHA" ;;
    tag)
      [[ "$EVENT_SHA" == "$EVENT_AFTER" ]] || die 'the event sha is a tag object other than the pushed one'
      git rev-parse "$EVENT_SHA^{commit}"
      ;;
    *) die 'the event sha is neither a commit nor the pushed tag object' ;;
  esac
}
case "$mode" in
  bind)
    git fetch --quiet --no-tags --force origin "refs/tags/$TAG:refs/tags/$TAG"
    object="$(git rev-parse "refs/tags/$TAG")"
    [[ "$(git cat-file -t "$object")" == tag ]] || die "$TAG is not an annotated tag"
    # The event must name the pushed annotated tag object itself. When it names
    # only a commit, the original object cannot be bound, so fail closed rather
    # than accept whatever tag object the ref holds now.
    [[ "$(git cat-file -t "$EVENT_AFTER" 2>/dev/null || true)" == tag ]] ||
      die 'the event does not name the pushed tag object (after is not an annotated tag object); refusing to bind'
    [[ "$object" == "$EVENT_AFTER" ]] || die "$TAG was replaced after the triggering push"
    commit="$(event_commit)"
    [[ "$(git rev-parse "$object^{commit}")" == "$commit" ]] || die "$TAG no longer points at the event commit"
    [[ "$(git rev-parse HEAD)" == "$commit" ]] || die 'the checkout is not the event commit'
    [[ "$(remote_object)" == "$object" ]] || die "$TAG on GitHub differs from the fetched tag"
    printf '%s\n' "$object"
    ;;
  verify)
    [[ "${TAG_OBJECT:-}" =~ $hex40 ]] || die 'TAG_OBJECT must be the bound tag object'
    [[ "$TAG_OBJECT" == "$EVENT_AFTER" ]] || die 'TAG_OBJECT is not the object the event named'
    [[ "$(git rev-parse "refs/tags/$TAG")" == "$TAG_OBJECT" ]] || die 'the local tag moved after binding'
    commit="$(event_commit)"
    [[ "$(git rev-parse HEAD)" == "$commit" ]] || die 'the checkout is not the event commit'
    [[ "$(git rev-parse "$TAG_OBJECT^{commit}")" == "$commit" ]] || die 'the bound tag does not peel to the event commit'
    [[ "$(remote_object)" == "$TAG_OBJECT" ]] || die "$TAG on GitHub moved after binding"
    # Pin, anchors (pinned checker), signing subkey and tagger come from the
    # tagged commit, which is also this checkout.
    STRUCTCORPUS_RELEASE_TAG="$TAG" "$root/scripts/verify-pinned-tag.sh" --published
    release_gh api "repos/$GITHUB_REPOSITORY/git/tags/$TAG_OBJECT" |
      jq -e --arg tag "$TAG" --arg commit "$commit" \
        '.tag == $tag and .object.type == "commit" and .object.sha == $commit and .verification.verified == true and .verification.reason == "valid"' \
        >/dev/null || die "GitHub does not report $TAG ($TAG_OBJECT) verified"
    [[ "$(remote_object)" == "$TAG_OBJECT" ]] || die "$TAG on GitHub moved during verification"
    echo "[ok] $TAG ($TAG_OBJECT) on $EVENT_SHA matches the pin in its commit and GitHub reports it verified"
    ;;
  *) die 'usage: release-ci-verify-tag.sh bind|verify' ;;
esac
