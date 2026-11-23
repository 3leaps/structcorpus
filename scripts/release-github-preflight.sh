#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# Verify the GitHub release settings that live outside the repository:
#
#   1. The "Tag Publish Protection" tag ruleset on 3leaps/structcorpus is active,
#      covers refs/tags/v* with no exclusions, requires creation, update,
#      deletion and non_fast_forward, and (when the caller has admin read access
#      to see bypass_actors) allows only OrganizationAdmin to bypass.
#   2. Immutable releases are enabled on 3leaps/structcorpus.
#
# Read-only: calls `gh api` GET endpoints only. Run by `make release-preflight`
# and standalone via `make release-github-preflight`.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=scripts/release-gh.sh
source "$root/scripts/release-gh.sh"

repo="3leaps/structcorpus"
ruleset_name="Tag Publish Protection"

die() {
  echo "error: $*" >&2
  exit 1
}

for tool in gh jq; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool not found in PATH"
done

rulesets_json="$(release_gh api "repos/$repo/rulesets?per_page=100")" ||
  die "could not read rulesets for $repo (check GitHub CLI auth status)"

ruleset_id="$(jq -r --arg name "$ruleset_name" '
	[ .[] | select(.name == $name and .target == "tag") ] |
	if length == 1 then .[0].id else empty end
' <<<"$rulesets_json")"
[[ -n "$ruleset_id" ]] ||
  die "expected exactly one tag ruleset named '$ruleset_name' on $repo"

ruleset="$(release_gh api "repos/$repo/rulesets/$ruleset_id")" ||
  die "could not read ruleset $ruleset_id on $repo"

# GitHub omits `bypass_actors` when the caller lacks repository admin access.
# An unseen bypass list could hide an extra actor able to rewrite v* tags, so
# the preflight fails closed: run it with a token that can read the list.
jq -e --arg repo "$repo" --arg name "$ruleset_name" '
	.name == $name and
	.source_type == "Repository" and
	.source == $repo and
	.target == "tag" and
	.enforcement == "active" and
	.conditions.ref_name.include == ["refs/tags/v*"] and
	.conditions.ref_name.exclude == [] and
	([.rules[].type] | sort) == [
		"creation",
		"deletion",
		"non_fast_forward",
		"update"
	] and
	([.rules[] | has("parameters")] | all(. == false)) and
	.bypass_actors == [
		{
			"actor_id": null,
			"actor_type": "OrganizationAdmin",
			"bypass_mode": "always"
		}
	]
' <<<"$ruleset" >/dev/null || {
  [[ "$(jq -r 'has("bypass_actors")' <<<"$ruleset")" == true ]] ||
    die "ruleset '$ruleset_name' ($ruleset_id) bypass list is not visible to this token; rerun with repository admin access"
  die "ruleset '$ruleset_name' ($ruleset_id) on $repo does not match the required tag protection policy"
}
echo "[ok] ruleset '$ruleset_name' ($ruleset_id): active, refs/tags/v* protected (OrganizationAdmin only)"

immutable="$(release_gh api "repos/$repo/immutable-releases")" ||
  die "could not read immutable-releases for $repo"
jq -e '.enabled == true' <<<"$immutable" >/dev/null ||
  die "immutable releases are not enabled on $repo"
echo "[ok] immutable releases: enabled on $repo"

echo "[ok] GitHub release preflight passed for $repo"
