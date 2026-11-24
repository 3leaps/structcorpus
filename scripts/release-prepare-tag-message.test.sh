#!/usr/bin/env bash
# No live key, GitHub operation, or tag: exercise only an isolated message fixture.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/repo/scripts" "$scratch/external" "$scratch/bin"
cp "$root/scripts/release-tag-operator.sh" "$root/scripts/release-prepare-tag-message.py" "$root/scripts/release-guard-tag-input.sh" \
  "$root/scripts/release-guard-release-surfaces.sh" "$scratch/repo/scripts/"
printf '1.2.3\n' >"$scratch/repo/VERSION"
# The section is copied as written: long lines, a "#" line that is not a
# heading, a bracketed line that is not a link definition, repeated blank
# lines, indented code, a table and tabs all survive unchanged.
{
  printf '# Changelog\n\n## [Unreleased]\n\n- Unreleased entry that must not appear.\n\n'
  printf '## [1.2.3] - 2026-01-02\n\n'
  printf 'Opening paragraph that\ncontinues here.\n\n### Added\n\n'
  printf -- '- First entry with `code` and a long sentence that is not rewrapped when it is drafted into the message.\n'
  printf '  Continuation line.\n#123 tracks this fix.\n[note] ordinary text, not a link definition.\n\n\n\n'
  printf '    indented code\n\n| a | b |\n|---|---|\n\ttabbed line\n\n'
  printf '## [1.2.2] - 2026-01-01\n\n- Older entry that must not appear.\n\n'
  printf '[Unreleased]: https://github.com/3leaps/structcorpus/compare/v1.2.3...HEAD\n'
  printf '[1.2.3]: https://github.com/3leaps/structcorpus/compare/v1.2.2...v1.2.3\n'
  printf '[1.2.2]: https://github.com/3leaps/structcorpus/releases/tag/v1.2.2\n'
} >"$scratch/changelog"
cp "$scratch/changelog" "$scratch/repo/CHANGELOG.md"
cat >"$scratch/bin/git" <<'SH'
#!/usr/bin/env bash
printf 'git operation attempted\n' >>"$TRACE"
exit 1
SH
chmod +x "$scratch/bin/git" "$scratch/repo/scripts/"*
export PATH="$scratch/bin:$PATH" TRACE="$scratch/trace" STRUCTCORPUS_RELEASE_TAG=v1.2.3
operator="$scratch/repo/scripts/release-tag-operator.sh"
directory="$scratch/external/v1.2.3"
export STRUCTCORPUS_TAG_MESSAGE_DIR="$directory"
expect_fail() {
  if "$@" >"$scratch/output" 2>&1; then
    echo 'error: expected message-preparation rejection' >&2
    exit 1
  fi
}
expect_fail env -u STRUCTCORPUS_RELEASE_TAG "$operator" prepare-message
expect_fail env STRUCTCORPUS_RELEASE_TAG=v1.2.4 "$operator" prepare-message
expect_fail env -u STRUCTCORPUS_TAG_MESSAGE_DIR "$operator" prepare-message
expect_fail env STRUCTCORPUS_TAG_MESSAGE_DIR=relative/v1.2.3 "$operator" prepare-message
expect_fail env STRUCTCORPUS_TAG_MESSAGE_DIR="$scratch/repo/v1.2.3" "$operator" prepare-message
[[ ! -e "$scratch/repo/v1.2.3" ]]
mkdir -p "$scratch/external/alternate"
mkdir -p "$scratch/external/shortcut"
ln -s "$scratch/external/alternate" "$scratch/external/shortcut/v1.2.3"
expect_fail env STRUCTCORPUS_TAG_MESSAGE_DIR="$scratch/external/shortcut/v1.2.3" "$operator" prepare-message
ln -s "$scratch/repo" "$scratch/external/inside-repo"
expect_fail env STRUCTCORPUS_TAG_MESSAGE_DIR="$scratch/external/inside-repo/v1.2.3" "$operator" prepare-message
ln -s "$scratch/external/alternate" "$scratch/external/outside-link"
expect_fail env STRUCTCORPUS_TAG_MESSAGE_DIR="$scratch/external/outside-link/v1.2.3" "$operator" prepare-message
[[ ! -e "$TRACE" ]]

# The draft comes from the dated changelog section of a changelog that passes
# the release-surface guard; otherwise nothing is created, not even the
# message directory.
changelog_refused() {
  expect_fail "$operator" prepare-message
  grep -q "$1" "$scratch/output"
  [[ ! -e "$directory" ]]
}
guard_refused='must pass the release-surface guard'
# with_section <body>: the fixture changelog with the 1.2.3 section body replaced.
with_section() {
  SECTION_BODY="$1" awk '
    /^## \[1\.2\.3\] - / { print; print ""; printf "%s", ENVIRON["SECTION_BODY"]; skip = 1; next }
    /^## / { skip = 0 }
    !skip
  ' "$scratch/changelog" >"$scratch/repo/CHANGELOG.md"
}
rm "$scratch/repo/CHANGELOG.md"
changelog_refused "$guard_refused"
with_section $'- Entry.\n```\ncode\n```\n\n'
changelog_refused "$guard_refused"
with_section $'- Entry.\n~~~\ncode\n~~~\n\n'
changelog_refused "$guard_refused"
with_section $'- Entry.\n[x]: https://example.invalid/\n\n## [1.2.2] - 2026-01-01\n\n- Hidden.\n\n'
changelog_refused "$guard_refused"
with_section $'- Entry with <html>.\n\n'
changelog_refused "$guard_refused"
with_section $'- Entry with \xc3\xa9.\n\n'
changelog_refused "$guard_refused"
with_section $'- Entry with \r carriage return.\n\n'
changelog_refused "$guard_refused"
{
  cat "$scratch/changelog"
  printf 'x\000\n'
} >"$scratch/repo/CHANGELOG.md"
changelog_refused "$guard_refused"
sed 's/^## \[1\.2\.3\] - 2026-01-02$/## [1.2.3]/' "$scratch/changelog" >"$scratch/repo/CHANGELOG.md"
changelog_refused "$guard_refused"
sed 's/^## \[1\.2\.2\] - 2026-01-01$/## [1.2.3] - 2026-01-01/' "$scratch/changelog" >"$scratch/repo/CHANGELOG.md"
changelog_refused "$guard_refused"
with_section $'\n\n'
changelog_refused 'section for 1.2.3 is empty'
# Changelogs the guard accepts, but where a line could start another section
# that would otherwise leak into the draft: refused, and nothing is created.
for boundary in ' ## [1.2.1] - 2026-01-01' '  ## [1.2.1] - 2026-01-01' '   ## [1.2.1] - 2026-01-01' \
  $'##\t[1.2.1] - 2026-01-01' '##' '#' '# Older' $'Older release\n---' $'Older release\n===' ' ---' \
  $'Older release\n=' $'Older release\n--' $'Older release\n=== ' $'Older release\n===\t' \
  $'Older release\n--- ' $'Older release\n---\t' $'Older release\n====' $'Older release\n----' \
  $'Older release\n===   ' $'Older release\n---   '; do
  with_section $'- Entry.\n\n'"$boundary"$'\n\n- Leaked.\n\n'
  "$scratch/repo/scripts/release-guard-release-surfaces.sh" >/dev/null
  changelog_refused 'could start another section'
done
# Controls: lines that cannot start a level-one or level-two section are drafted.
for line in '- Entry.' '### Added' '    ## indented code' $'\t## tab-indented code' '#hashtag' '##hashtag' \
  '=== not an underline' '-- not an underline'; do
  with_section $'- Entry.\n\n'"$line"$'\n\n- Kept.\n\n'
  "$scratch/repo/scripts/release-guard-release-surfaces.sh" >/dev/null
  "$operator" prepare-message >"$scratch/output"
  grep -qxF -- "$line" "$directory/v1.2.3.txt"
  grep -q '^- Kept\.$' "$directory/v1.2.3.txt"
  rm -r "$directory"
done
rm "$scratch/repo/scripts/release-guard-release-surfaces.sh"
cp "$scratch/changelog" "$scratch/repo/CHANGELOG.md"
changelog_refused 'unable to prepare external tag message'
# Any nonzero guard status refuses, not only status 1, and so does a guard
# killed by a signal.
for guard_body in 'exit 2' 'kill -TERM $$'; do
  printf '#!/usr/bin/env bash\n%s\n' "$guard_body" >"$scratch/repo/scripts/release-guard-release-surfaces.sh"
  chmod +x "$scratch/repo/scripts/release-guard-release-surfaces.sh"
  changelog_refused "$guard_refused"
done
cp "$root/scripts/release-guard-release-surfaces.sh" "$scratch/repo/scripts/"
[[ ! -e "$TRACE" ]]

# Trailing whitespace is copied too, and the message is reported incomplete
# for it rather than silently trimmed.
with_section $'- Entry with a trailing space. \n\n'
"$operator" prepare-message >"$scratch/output"
grep -q '^- Entry with a trailing space\. $' "$directory/v1.2.3.txt"
grep -q 'incomplete: tag message needs one final newline and no CR, NUL or trailing whitespace' "$scratch/output"
rm -r "$directory"

# Section selection refuses duplicate and undated headings by itself, though the
# guard already does.
python3 -I -B - "$scratch/repo/scripts/release-prepare-tag-message.py" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("prepare", sys.argv[1])
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
for text in (
    "## [1.2.3] - 2026-01-02\n\n- One.\n\n## [1.2.3] - 2026-01-03\n\n- Two.\n",
    "## [1.2.3] - Unreleased\n\n- One.\n",
    "## [1.2.3] - 2026-01-02 (draft)\n\n- One.\n",
    "## [1.2.3] - 2026-1-2\n\n- One.\n",
    "## [1.2.3] - 026-01-02\n\n- One.\n",
    "## [1.2.3] - 20260-01-02\n\n- One.\n",
    "## [1.2.3] - 2026-1-02\n\n- One.\n",
    "## [1.2.3] - 2026-01-2\n\n- One.\n",
    "## [1.2.3] - 2026-001-02\n\n- One.\n",
    "## [1.2.3] - 2026-01-002\n\n- One.\n",
):
    try:
        prepare.changelog_section(text, "1.2.3")
    except ValueError as error:
        assert "exactly one dated section" in str(error), error
    else:
        sys.exit(f"error: section heading was accepted: {text.splitlines()[0]!r}")

# Every blank or whitespace-only line around the body is trimmed; inner ones stay.
text = "## [1.2.3] - 2026-01-02\n\n\n \n\t\n- One.\n\n- Two.\n\n \n\t\n\n## [1.2.2] - 2026-01-01\n"
body = prepare.changelog_section(text, "1.2.3")
assert body == ["- One.", "", "- Two."], body

# The body starts on the line after the heading, blank or not.
text = "## [1.2.3] - 2026-01-02\n- One.\n- Two.\n"
body = prepare.changelog_section(text, "1.2.3")
assert body == ["- One.", "- Two."], body

# Any link definition ends the section, whichever definition comes first.
text = (
    "## [1.2.3] - 2026-01-02\n\n- One.\n\n"
    "[1.2.3]: https://github.com/3leaps/structcorpus/releases/tag/v1.2.3\n"
    "[Unreleased]: https://github.com/3leaps/structcorpus/compare/v1.2.3...HEAD\n"
)
body = prepare.changelog_section(text, "1.2.3")
assert body == ["- One."], body

# Any level-two heading ends the section, not only a release heading.
text = "## [1.2.3] - 2026-01-02\n\n- One.\n\n## Notes\n\n- Not part of the release.\n"
body = prepare.changelog_section(text, "1.2.3")
assert body == ["- One."], body
PY

# A first release's section ends at the link-definition footer.
{
  printf '# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-01-02\n\n- Only entry.\n\n'
  printf '[Unreleased]: https://github.com/3leaps/structcorpus/compare/v1.2.3...HEAD\n'
  printf '[1.2.3]: https://github.com/3leaps/structcorpus/releases/tag/v1.2.3\n'
} >"$scratch/repo/CHANGELOG.md"
"$operator" prepare-message >"$scratch/output"
printf 'Release 1.2.3\n\n<REVIEW AND EDIT THE DRAFT BELOW THEN DELETE THIS LINE>\n\n- Only entry.\n\nRole: <role>\nCo-authored-by: <model> <noreply@3leaps.net>\nCommitter-of-Record: @3leapsdave\n' >"$scratch/expected-first"
cmp "$scratch/expected-first" "$directory/v1.2.3.txt"
rm -r "$directory"
cp "$scratch/changelog" "$scratch/repo/CHANGELOG.md"

"$operator" prepare-message >"$scratch/output"
[[ -f "$directory/v1.2.3.txt" ]]
{
  printf 'Release 1.2.3\n\n<REVIEW AND EDIT THE DRAFT BELOW THEN DELETE THIS LINE>\n\n'
  printf 'Opening paragraph that\ncontinues here.\n\n### Added\n\n'
  printf -- '- First entry with `code` and a long sentence that is not rewrapped when it is drafted into the message.\n'
  printf '  Continuation line.\n#123 tracks this fix.\n[note] ordinary text, not a link definition.\n\n\n\n'
  printf '    indented code\n\n| a | b |\n|---|---|\n\ttabbed line\n\n'
  printf 'Role: <role>\nCo-authored-by: <model> <noreply@3leaps.net>\nCommitter-of-Record: @3leapsdave\n'
} >"$scratch/expected-draft"
cmp "$scratch/expected-draft" "$directory/v1.2.3.txt"
# Completing only the footer is not enough: the review marker still refuses.
sed -e 's/^Role: <role>$/Role: devlead/' -e 's/<model>/Example Model/' "$directory/v1.2.3.txt" >"$scratch/footer-only"
if "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$scratch/footer-only" 'Release 1.2.3' 2>"$scratch/marker-output"; then
  echo 'error: a draft with its review marker was accepted' >&2
  exit 1
fi
grep -q 'unresolved placeholder' "$scratch/marker-output"
sed -e '3,4d' "$scratch/footer-only" >"$scratch/reviewed"
"$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$scratch/reviewed" 'Release 1.2.3'
grep -q '^Release 1.2.3$' "$directory/v1.2.3.txt"
grep -q '^Role: <role>$' "$directory/v1.2.3.txt"
grep -q '^Co-authored-by: <model> <noreply@3leaps\.net>$' "$directory/v1.2.3.txt"
grep -q '^Committer-of-Record: @3leapsdave$' "$directory/v1.2.3.txt"
grep -q '^\[\.\.\] created v1.2.3.txt (incomplete:' "$scratch/output"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt" 'Release 1.2.3'

cat >"$directory/v1.2.3.txt" <<'EOF'
Release 1.2.3

Custom approved summary.

Role: devlead
Co-authored-by: Example Model <noreply@3leaps.net>
Committer-of-Record: @3leapsdave
EOF
"$operator" prepare-message >"$scratch/output"
grep -q '^\[ok\] preserved v1.2.3.txt (complete):' "$scratch/output"
grep -q 'Custom approved summary.' "$directory/v1.2.3.txt"
"$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt" 'Release 1.2.3'

printf 'Generated by <model>\n' >"$directory/v1.2.3.txt"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt"
printf 'Release 1.2.3\n\nSummary <TODO-version>\n\nRole: devlead\nCo-authored-by: Example Model <noreply@3leaps.net>\nCommitter-of-Record: @3leapsdave\n' >"$directory/v1.2.3.txt"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt"
printf 'Release 1.2.3\n\nSummary.\n\nGenerated by Model via Tool under supervision of @3leapsdave\n\nRole: devlead\nCo-authored-by: Example Model <noreply@3leaps.net>\nCommitter-of-Record: @3leapsdave\n' >"$directory/v1.2.3.txt"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt"
printf 'Release 1.2.3\n\nMissing footer.\n' >"$directory/v1.2.3.txt"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt"
printf 'Release 1.2.3 \n\nBad trailing space.\n\nRole: devlead\nCo-authored-by: Example Model <noreply@3leaps.net>\nCommitter-of-Record: @3leapsdave\n' >"$directory/v1.2.3.txt"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt"
printf 'Release 1.2.3\n\nSummary.\n\nRole: devlead\nCo-authored-by: Example Model <noreply@3leaps.dev>\nCommitter-of-Record: @3leapsdave\n' >"$directory/v1.2.3.txt"
expect_fail "$scratch/repo/scripts/release-prepare-tag-message.py" --validate-message "$directory/v1.2.3.txt"
rm "$directory/v1.2.3.txt"
ln -s "$scratch/external/alternate" "$directory/v1.2.3.txt"
expect_fail "$operator" prepare-message
rm "$directory/v1.2.3.txt"
cat >"$directory/v1.2.3.txt" <<'EOF'
Release 1.2.3

Custom approved summary.

Role: devlead
Co-authored-by: Example Model <noreply@3leaps.net>
Committer-of-Record: @3leapsdave
EOF

# Optional external loader works even with no signing variables; sourcing it
# changes directory, which the operator must restore before preparing text.
cat >"$scratch/external/loader" <<'SH'
cd "$FIXTURE_AWAY"
export STRUCTCORPUS_TAG_MESSAGE_DIR="$FIXTURE_MESSAGE_DIR"
SH
export FIXTURE_AWAY="$scratch/external" FIXTURE_MESSAGE_DIR="$directory"
env -u STRUCTCORPUS_TAG_MESSAGE_DIR STRUCTCORPUS_APPROVED_ENV_LOADER="$scratch/external/loader" \
  "$operator" prepare-message >"$scratch/output"
grep -q 'Custom approved summary.' "$scratch/output"
[[ ! -e "$TRACE" ]]
echo '[ok] external message creation, changelog draft and review marker, review, no-clobber and unsafe-path controls passed'
