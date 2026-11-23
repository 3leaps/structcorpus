#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# release-guard-release-surfaces.sh - Verify CHANGELOG.md matches VERSION
#
# The changelog is maintained by hand and can fall behind VERSION without any
# other check failing, so the repository can present a stale release surface
# from a green tree. This guard asserts they moved together.
#
# Checks, against the version in VERSION:
# - CHANGELOG.md uses [Unreleased] and [<version>] exactly once each, as the
#   plain headings "## [Unreleased]" and "## [<version>] - YYYY-MM-DD"
# - link definitions follow a restricted grammar that leaves no Markdown
#   ambiguity: printable ASCII only, no "<" and no fence delimiters anywhere,
#   every definition in one
#   footer block at the end of the file (after a blank line), one canonical
#   "[label]: https://..." per line, and no "]:" anywhere outside the footer
# - the footer defines "[<version>]" exactly once, pointing at this repository:
#   compare/v<earlier>...v<version>, or releases/tag/v<version> for the first
#   release
# - the footer defines [Unreleased] exactly once, as
#   compare/v<version>...HEAD in this repository
#
# Usage: ./scripts/release-guard-release-surfaces.sh

set -euo pipefail

REPO_URL="https://github.com/3leaps/structcorpus"

# version_lt <a> <b>: true when x.y.z version a sorts strictly before b. Each
# component is compared as a decimal string (leading zeros dropped, then length,
# then digits), so arbitrarily long components cannot overflow shell arithmetic.
version_lt() {
  local IFS=.
  local -a a=($1) b=($2)
  local i x y
  for i in 0 1 2; do
    x="${a[i]#"${a[i]%%[!0]*}"}"
    y="${b[i]#"${b[i]%%[!0]*}"}"
    if [ "${#x}" -ne "${#y}" ]; then
      [ "${#x}" -lt "${#y}" ]
      return
    fi
    if [ "${x}" != "${y}" ]; then
      [[ "${x}" < "${y}" ]]
      return
    fi
  done
  return 1
}

# split_footer <text>: prints "<footer-start-line>" (1-based) of the trailing
# block of lines that begin with "[", after trailing blank lines are ignored.
# Prints 0 when there is no such block or it is not preceded by a blank line.
split_footer() {
  LC_ALL=C awk '
        { line[NR] = $0 }
        END {
            n = NR
            while (n > 0 && line[n] ~ /^[ \t]*$/) n--
            start = n + 1
            while (start > 1 && substr(line[start - 1], 1, 1) == "[") start--
            if (start > n || start == 1 || line[start - 1] !~ /^[ \t]*$/) { print 0; exit }
            print start
        }
    ' <<<"$1"
}

# validate_release_surfaces <version> <changelog> [repo_url]
validate_release_surfaces() {
  local version="$1"
  local changelog="$2"
  local repo="${3:-$REPO_URL}"

  if [ -z "${version}" ]; then
    echo "error: VERSION is empty" >&2
    return 1
  fi
  # Components are canonical and at most nine digits, which keeps every
  # footer label far below the 999-character limit beyond which Markdown no
  # longer reads a line as a link definition.
  if [[ ! "${version}" =~ ^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$ ]]; then
    echo "error: VERSION ${version} is not x.y.z" >&2
    return 1
  fi
  local escaped="${version//./\\.}"

  local start body footer defs count line earlier
  # Character-level rules close whole classes of Markdown ambiguity at once,
  # wherever they appear (column zero, list items, blockquotes, inline):
  # printable ASCII only (no byte-order mark, Unicode spaces or control
  # characters), no "<" (no raw HTML or autolinks), and no fence delimiters.
  if LC_ALL=C grep -q $'[^\t -~]' <<<"${changelog}"; then
    echo "error: CHANGELOG.md must contain only printable ASCII, tabs and newlines" >&2
    return 1
  fi
  if LC_ALL=C grep -q '<' <<<"${changelog}"; then
    echo "error: CHANGELOG.md must not contain '<' (raw HTML or autolinks)" >&2
    return 1
  fi
  if LC_ALL=C grep -qE '```|~~~' <<<"${changelog}"; then
    echo "error: CHANGELOG.md must not contain fenced code blocks" >&2
    return 1
  fi
  start="$(split_footer "${changelog}")"
  if [ "${start}" = 0 ]; then
    echo "error: CHANGELOG.md must end with a link-definition footer after a blank line" >&2
    return 1
  fi
  body="$(LC_ALL=C sed -n "1,$((start - 1))p" <<<"${changelog}")"
  footer="$(LC_ALL=C sed -n "${start},\$p" <<<"${changelog}" | LC_ALL=C sed -e :a -e '/^[ \t]*$/{$d;N;ba' -e '}')"
  if LC_ALL=C grep -q ']:' <<<"${body}"; then
    echo "error: CHANGELOG.md has a link definition outside the footer" >&2
    return 1
  fi

  # The required labels are used exactly once each, as plain section
  # headings, so no inline link, reference override, code span, image,
  # escape, indentation or deletion can replace or hide the rendered link.
  # Match from a here-string, never a pipe: grep -q exits on the first hit
  # and, under pipefail, the producer's SIGPIPE would turn a match into a
  # false failure once CHANGELOG is large enough.
  local uses
  uses="$(LC_ALL=C grep -iE '\[unreleased\]' <<<"${body}" || true)"
  if [ "${uses}" != "## [Unreleased]" ]; then
    echo "error: CHANGELOG.md must use [Unreleased] exactly once, as the heading '## [Unreleased]'" >&2
    return 1
  fi
  uses="$(LC_ALL=C grep -E "\[${escaped}\]" <<<"${body}" || true)"
  if [[ ! "${uses}" =~ ^##\ \[${escaped}\]\ -\ [0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "error: CHANGELOG.md has no section for [${version}] (it must use [${version}] exactly once, as '## [${version}] - YYYY-MM-DD')" >&2
    return 1
  fi
  # Every footer destination is one of this repository's fixed URL shapes, so
  # no destination can carry Markdown syntax (parentheses, escapes, spaces)
  # that would turn the footer back into paragraph text.
  local v='(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})' base
  base="$(sed 's/[.]/\\./g' <<<"${repo}")"
  if LC_ALL=C grep -vqE "^\[(${v}|[Uu]nreleased)\]: ${base}/(compare/v${v}\.\.\.(v${v}|HEAD)|releases/tag/v${v})\$" <<<"${footer}"; then
    echo "error: CHANGELOG.md footer lines must each be a canonical [label]: https://... definition for this repository" >&2
    return 1
  fi

  defs="$(LC_ALL=C grep -E "^\[${escaped}\]: " <<<"${footer}" || true)"
  count="$(grep -c . <<<"${defs}" || true)"
  if [ "${count}" != 1 ]; then
    echo "error: CHANGELOG.md must define the [${version}] link exactly once (found ${count})" >&2
    return 1
  fi
  line="${defs}"
  if [ "${line}" != "[${version}]: ${repo}/releases/tag/v${version}" ]; then
    if [[ "${line}" =~ ^\[${escaped}\]:\ (.*)/compare/v((0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8}))\.\.\.v${escaped}$ ]] &&
      [ "${BASH_REMATCH[1]}" = "${repo}" ]; then
      earlier="${BASH_REMATCH[2]}"
      if ! version_lt "${earlier}" "${version}"; then
        echo "error: CHANGELOG.md [${version}] link compares from v${earlier}, which is not earlier" >&2
        return 1
      fi
    else
      echo "error: CHANGELOG.md [${version}] link must be ${repo}/compare/v<earlier>...v${version} or ${repo}/releases/tag/v${version}" >&2
      return 1
    fi
  fi

  defs="$(LC_ALL=C grep -E '^\[[Uu]nreleased\]: ' <<<"${footer}" || true)"
  count="$(grep -c . <<<"${defs}" || true)"
  if [ "${count}" != 1 ]; then
    echo "error: CHANGELOG.md must define the [Unreleased] link exactly once (found ${count})" >&2
    return 1
  fi
  if [ "${defs}" != "[${defs:1:10}]: ${repo}/compare/v${version}...HEAD" ]; then
    echo "error: CHANGELOG.md [Unreleased] link must be ${repo}/compare/v${version}...HEAD" >&2
    return 1
  fi

  return 0
}

# reject_nul <file>: shell command substitution silently drops NUL bytes, so a
# file containing one must be refused before its content is read.
reject_nul() {
  if [ "$(LC_ALL=C tr -d '\000' <"$1" | wc -c)" != "$(wc -c <"$1")" ]; then
    echo "error: $(basename "$1") contains a NUL byte" >&2
    return 1
  fi
}

main() {
  local script_dir repo_root version changelog

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/.." && pwd)"

  if [ ! -f "${repo_root}/VERSION" ]; then
    echo "error: VERSION file not found" >&2
    exit 1
  fi
  version="$(tr -d '[:space:]' <"${repo_root}/VERSION")"

  if [ ! -f "${repo_root}/CHANGELOG.md" ]; then
    echo "error: CHANGELOG.md not found" >&2
    exit 1
  fi
  reject_nul "${repo_root}/CHANGELOG.md" || exit 1
  changelog="$(cat "${repo_root}/CHANGELOG.md")"

  if ! validate_release_surfaces "${version}" "${changelog}"; then
    echo "hint: run make sync-changelog-links, then see RELEASE_CHECKLIST.md" >&2
    exit 1
  fi

  echo "[ok] release surfaces match VERSION ${version}"
}

# Only run main when executed directly, so the negative controls can source this
# file and drive validate_release_surfaces with mutated content.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi
