#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=scripts/release-guard-tag-input.sh
source "$(dirname "$0")/release-guard-tag-input.sh"
release_guard_tag_input || exit 1
# shellcheck source=scripts/release-tag-common.sh
source "$(dirname "$0")/release-tag-common.sh"
cd "$tag_root"
"$tag_root/scripts/release-verify-tag.sh"
local_object="$(git rev-parse "refs/tags/$STRUCTCORPUS_RELEASE_TAG")"
remote_object="$(release_gh api "repos/3leaps/structcorpus/git/ref/tags/$STRUCTCORPUS_RELEASE_TAG" --jq 'select(.object.type == "tag") | .object.sha' 2>/dev/null || true)"
[[ -n "$remote_object" && "$remote_object" == "$local_object" ]] || tag_die 'remote tag object differs from local tag'
tag_ref="$(release_gh api "repos/3leaps/structcorpus/git/ref/tags/$STRUCTCORPUS_RELEASE_TAG")"
[[ "$(jq -r '.object.type' <<<"$tag_ref")" == tag && "$(jq -r '.object.sha' <<<"$tag_ref")" == "$local_object" ]] || tag_die 'GitHub tag ref mismatch'
tag_json="$(release_gh api "repos/3leaps/structcorpus/git/tags/$local_object")"
jq -e --arg commit "$(git rev-parse HEAD)" --arg tag "$STRUCTCORPUS_RELEASE_TAG" \
  '.tag == $tag and .object.type == "commit" and .object.sha == $commit and .verification.verified == true and .verification.reason == "valid"' \
  <<<"$tag_json" >/dev/null || tag_die 'GitHub does not report verified tag at HEAD'
echo '[ok] remote signed tag matches local object and GitHub verification'
