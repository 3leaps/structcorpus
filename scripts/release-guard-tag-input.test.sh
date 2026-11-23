#!/usr/bin/env bash
# Controls for the explicit release-tag input (PDR-0008 section 2.4): the
# generic RELEASE_TAG alias is refused from every origin, even when empty, at
# every tag-consuming Make target and direct entrypoint, before any loader,
# fetch, message or tag side effect; and no tag is derived from VERSION.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
cd "$root"
unset RELEASE_TAG STRUCTCORPUS_RELEASE_TAG STRUCTCORPUS_APPROVED_ENV_LOADER
version="$(tr -d ' \t\r\n' <VERSION)"
good="v$version"

refused() { # refused PATTERN CMD...: CMD fails and says PATTERN
  local pattern="$1"
  shift
  if "$@" >"$scratch/out" 2>&1; then
    echo "error: accepted: $*" >&2
    exit 1
  fi
  grep -q -- "$pattern" "$scratch/out" || {
    echo "error: refused for another reason than '$pattern': $*" >&2
    cat "$scratch/out" >&2
    exit 1
  }
}

# The guard itself.
./scripts/release-guard-tag-input.sh >/dev/null 2>&1 && {
  echo 'error: guard accepted a missing tag' >&2
  exit 1
}
refused 'is required' env -u STRUCTCORPUS_RELEASE_TAG ./scripts/release-guard-tag-input.sh
for bad in "$version" "v$version " "v$version-rc.1" vv1.2.3 v01.2.3; do
  refused 'must be canonical' env STRUCTCORPUS_RELEASE_TAG="$bad" ./scripts/release-guard-tag-input.sh
done
for alias in "$good" ''; do
  refused 'generic RELEASE_TAG alias is forbidden' env RELEASE_TAG="$alias" STRUCTCORPUS_RELEASE_TAG="$good" ./scripts/release-guard-tag-input.sh
done
env STRUCTCORPUS_RELEASE_TAG="$good" ./scripts/release-guard-tag-input.sh

# Make: command-line and environment origins, on every tag-consuming target.
# -n proves the refusal happens while Make expands the guard, before any recipe.
targets=(release-preflight release-guard-tag-name release-guard-tag-version release-guard-signing-tag
  release-prepare-tag-message release-tag release-push-tag release-verify-tag
  release-verify-published-tag release-verify-remote-tag)
for target in "${targets[@]}"; do
  refused 'origin: command line' make --no-print-directory -n "$target" RELEASE_TAG=v9.9.9 STRUCTCORPUS_RELEASE_TAG="$good"
  refused 'origin: environment' env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$good" make --no-print-directory -n "$target"
  refused 'is required' env -u STRUCTCORPUS_RELEASE_TAG make --no-print-directory "$target"
done

# Direct entrypoints, bypassing Make.
for script in release-preflight.sh release-verify-tag.sh release-verify-remote-tag.sh \
  release-verify-published-tag.sh verify-pinned-tag.sh release-tag.sh release-push-tag.sh; do
  refused 'generic RELEASE_TAG alias is forbidden' env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$good" "./scripts/$script"
done
for mode in prepare-message local-tag remote-push; do
  refused 'generic RELEASE_TAG alias is forbidden' env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$good" ./scripts/release-tag-operator.sh "$mode"
  refused 'is required' env -u STRUCTCORPUS_RELEASE_TAG ./scripts/release-tag-operator.sh "$mode"
done
refused 'generic RELEASE_TAG alias is forbidden' env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$good" \
  STRUCTCORPUS_TAG_MESSAGE_DIR="$scratch/$good" python3 -I -B ./scripts/release-prepare-tag-message.py
[[ ! -e "$scratch/$good" ]] || {
  echo 'error: a message directory was touched after a refused alias' >&2
  exit 1
}

# Relative invocation: from scripts/ and from outside the repository root.
repo_name="$(basename "$root")"
for script in release-preflight.sh release-verify-tag.sh release-verify-remote-tag.sh \
  release-verify-published-tag.sh verify-pinned-tag.sh release-tag.sh release-push-tag.sh \
  release-tag-operator.sh; do
  refused 'generic RELEASE_TAG alias is forbidden' bash -c 'cd "$1/scripts" && exec env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$2" "./$3" prepare-message' _ "$root" "$good" "$script"
  refused 'generic RELEASE_TAG alias is forbidden' bash -c 'cd "$1/.." && exec env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$2" "./$4/scripts/$3" prepare-message' _ "$root" "$good" "$script" "$repo_name"
done

# The operator refuses an alias before its optional loader runs, and again if
# the loader itself sets one.
printf 'touch %q\n' "$scratch/loader-ran" >"$scratch/loader.sh"
refused 'generic RELEASE_TAG alias is forbidden' env RELEASE_TAG= STRUCTCORPUS_RELEASE_TAG="$good" \
  STRUCTCORPUS_APPROVED_ENV_LOADER="$scratch/loader.sh" ./scripts/release-tag-operator.sh prepare-message
[[ ! -e "$scratch/loader-ran" ]] || {
  echo 'error: the loader ran before the alias was refused' >&2
  exit 1
}
printf 'export RELEASE_TAG=v9.9.9\n' >"$scratch/alias-loader.sh"
refused 'generic RELEASE_TAG alias is forbidden' env STRUCTCORPUS_RELEASE_TAG="$good" \
  STRUCTCORPUS_APPROVED_ENV_LOADER="$scratch/alias-loader.sh" ./scripts/release-tag-operator.sh prepare-message

echo '[ok] release tag input: alias refused from every origin and entrypoint before side effects; no derived default'
