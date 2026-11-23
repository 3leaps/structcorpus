#!/usr/bin/env bash
# The release tag is an explicit input (PDR-0008 section 2.4): refuse the
# generic RELEASE_TAG alias whenever it is set, even to an empty value, and
# require a canonical STRUCTCORPUS_RELEASE_TAG. Never derives a tag. Run, or
# source, before any loader, fetch, message or tag side effect.
release_guard_tag_input() {
  if [[ -n "${RELEASE_TAG+set}" ]]; then
    echo 'error: generic RELEASE_TAG alias is forbidden; unset it and use STRUCTCORPUS_RELEASE_TAG' >&2
    return 1
  fi
  [[ -n "${STRUCTCORPUS_RELEASE_TAG:-}" ]] || {
    echo 'error: STRUCTCORPUS_RELEASE_TAG is required (no default is derived)' >&2
    return 1
  }
  [[ "$STRUCTCORPUS_RELEASE_TAG" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
    echo 'error: STRUCTCORPUS_RELEASE_TAG must be canonical vX.Y.Z' >&2
    return 1
  }
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  release_guard_tag_input
fi
