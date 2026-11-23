#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# surface-scan.sh enforces its gate against a synthetic catalog built here at
# run time (invented terms, not the maintainer's): a term in the tree, a commit
# message, the PR text or the branch name fails; the catalog must block its own
# canary; a scanner error or a bad report fails closed and visibly; the catalog
# path rules hold. The baseline-only mode used by CI must block its built-in
# sentinel on every surface and refuse a catalog. Needs limensafe; without it
# this suite is skipped.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
bin="${STRUCTCORPUS_LIMENSAFE_BIN:-$(command -v limensafe || true)}"
if [[ -z "$bin" || ! -x "$bin" ]]; then
  echo '[skip] surface-scan controls: limensafe is not installed'
  exit 0
fi
scratch="$(mktemp -d)"
trap 'rc=$?; rm -rf "$scratch"; exit "$rc"' EXIT
unset LIMENSAFE_CATALOG_PATH STRUCTCORPUS_SURFACE_PR_TEXT STRUCTCORPUS_SURFACE_SCAN_REQUIRED STRUCTCORPUS_SURFACE_SCOPE \
  STRUCTCORPUS_SURFACE_BASELINE_ONLY STRUCTCORPUS_SURFACE_BRANCH_NAME STRUCTCORPUS_SURFACE_BASE
term="zq""lantern" canary="gon-test-canary-""7f3e19a2" sentinel="DO_NOT_""COMMIT"
printf '%s==>Codename\n%s==>StructcorpusCanary\n' "$term" "$canary" >"$scratch/terms.txt"
"$bin" catalog build --from-termlist "$scratch/terms.txt" --out "$scratch/catalog.yaml" \
  --catalog-id structcorpus-release >/dev/null 2>&1
printf '%s==>StructcorpusCanary\n' "$canary" >"$scratch/onlycanary.txt"
"$bin" catalog build --from-termlist "$scratch/onlycanary.txt" --out "$scratch/onlycanary.yaml" \
  --catalog-id structcorpus-release >/dev/null 2>&1
printf '%s==>Codename\n' "$term" >"$scratch/nocanary.txt"
"$bin" catalog build --from-termlist "$scratch/nocanary.txt" --out "$scratch/nocanary.yaml" \
  --catalog-id structcorpus-release >/dev/null 2>&1
printf '%s==>Codename\n%s==>StructcorpusCanary\n' "$term" "$canary" >"$scratch/otherid.txt"
"$bin" catalog build --from-termlist "$scratch/otherid.txt" --out "$scratch/otherid.yaml" \
  --catalog-id some-other-catalog >/dev/null 2>&1

repo="$scratch/repo"
git init -q -b main "$repo"
git -C "$repo" config core.autocrlf false
git -C "$repo" config user.name fixture
git -C "$repo" config user.email fixture@example.invalid
git -C "$repo" config commit.gpgsign false
mkdir -p "$repo/scripts"
cp "$root/scripts/surface-scan.sh" "$root/scripts/surface-canary.py" "$root/scripts/surface-catalog-path.py" \
  "$root/scripts/export-committed-tree.py" "$root/scripts/committed_tree.py" "$repo/scripts/"
printf 'clean\n' >"$repo/README"
git -C "$repo" add -A
git -C "$repo" commit -qm 'clean base'
git -C "$repo" update-ref refs/remotes/origin/main HEAD
git -C "$repo" switch -q -c feature

scan() { (cd "$repo" && env PYTHON="${PYTHON:-python3}" STRUCTCORPUS_LIMENSAFE_BIN="$bin" "$@" scripts/surface-scan.sh) >"$scratch/out" 2>&1; }
passes() { scan "$@" || {
  echo "error: refused: $*" >&2
  cat "$scratch/out" >&2
  exit 1
}; }
refused() {
  local reason="$1"
  shift
  if scan "$@"; then
    echo "error: accepted, expected: $reason" >&2
    cat "$scratch/out" >&2
    exit 1
  fi
  grep -q -- "$reason" "$scratch/out" || {
    echo "error: refused for another reason than '$reason'" >&2
    cat "$scratch/out" >&2
    exit 1
  }
}
cat_ok=(LIMENSAFE_CATALOG_PATH="$scratch/catalog.yaml")

passes ${cat_ok[@]+"${cat_ok[@]}"}
grep -q '\[ok\] catalog blocks its canary' "$scratch/out"
passes env -u LIMENSAFE_CATALOG_PATH
grep -q '\[skip\] surface scan' "$scratch/out"
refused 'LIMENSAFE_CATALOG_PATH is required' STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1
refused 'set but empty' LIMENSAFE_CATALOG_PATH=
refused 'must be an absolute path' LIMENSAFE_CATALOG_PATH=catalog.yaml
refused 'does not name a readable file' LIMENSAFE_CATALOG_PATH="$scratch/absent.yaml"
cp "$scratch/catalog.yaml" "$repo/inside.yaml"
refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$repo/inside.yaml"
ln -s "$repo" "$scratch/repo-link"
refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$scratch/repo-link/inside.yaml"
ln -s "$repo/inside.yaml" "$scratch/outside-link.yaml"
refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$scratch/outside-link.yaml"
rm -f "$repo/inside.yaml"
cp "$scratch/catalog.yaml" "$scratch/linked.yaml"
ln "$scratch/linked.yaml" "$repo/linked-inside.yaml"
refused 'hard link' LIMENSAFE_CATALOG_PATH="$scratch/linked.yaml"
rm -f "$repo/linked-inside.yaml"
cp "$scratch/catalog.yaml" "$repo/inside.yaml"
cp "$scratch/catalog.yaml" "$repo/123"
upper="$(dirname "$repo")/$(basename "$repo" | tr '[:lower:]' '[:upper:]')"
if [[ -e "$upper/inside.yaml" ]]; then
  refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$upper/inside.yaml"
  refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$upper/123"
  case_checked=1
fi
rm -f "$repo/inside.yaml" "$repo/123"
cp "$scratch/catalog.yaml" "$scratch/outside.yaml"
ln -s "$scratch/outside.yaml" "$repo/link-to-outside.yaml"
refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$repo/link-to-outside.yaml"
rm -f "$repo/link-to-outside.yaml"
mkdir -p "$repo/sub"
cp "$scratch/catalog.yaml" "$repo/inside.yaml"
refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$repo/sub/../inside.yaml"
rm -rf "$repo/sub" "$repo/inside.yaml"
git -C "$repo" worktree add -q --detach "$scratch/wt" HEAD
cp "$scratch/catalog.yaml" "$scratch/wt/inside.yaml"
refused 'outside this repository' LIMENSAFE_CATALOG_PATH="$scratch/wt/inside.yaml"
git -C "$repo" worktree remove --force "$scratch/wt"
refused 'no usable canary' LIMENSAFE_CATALOG_PATH="$scratch/nocanary.yaml"
refused 'no entity besides StructcorpusCanary' LIMENSAFE_CATALOG_PATH="$scratch/onlycanary.yaml"
refused 'catalog structcorpus-release did not load' LIMENSAFE_CATALOG_PATH="$scratch/otherid.yaml"
printf '#!/bin/sh\necho boom >&2\nexit 7\n' >"$scratch/broken"
chmod +x "$scratch/broken"
refused 'limensafe exited 7' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/broken"
printf '#!/bin/sh\nexit 0\n' >"$scratch/silent"
chmod +x "$scratch/silent"
refused 'report is missing or invalid' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/silent"
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"structcorpus-release","load_status":"ok"},{"catalog_id":"limensafe-public-baseline-v0","load_status":"ok"}],"files_skipped_by_reason":{},"directories_skipped":0},"summary":{"findings_total":1},"findings":[{"decision":"block","replacement_id":"Codename","severity":"high"}]}'"'"'\nexit 1\n' >"$scratch/wrongblock"
chmod +x "$scratch/wrongblock"
refused 'not blocked as StructcorpusCanary' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/wrongblock"
cat >"$scratch/flaky" <<SH
#!/bin/sh
count_file="$scratch/flaky.count"
n=\$(cat "\$count_file" 2>/dev/null || echo 0); n=\$((n + 1)); echo "\$n" >"\$count_file"
[ "\$n" -le 2 ] && exec "$bin" "\$@"
exit 0
SH
chmod +x "$scratch/flaky"
printf 'more\n' >"$repo/more.txt"
git -C "$repo" add -A
git -C "$repo" commit -qm 'a clean commit message'
rm -f "$scratch/flaky.count"
refused 'commit .*: limensafe report is missing or invalid' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/flaky"
git -C "$repo" reset -q --hard HEAD~1
printf '#!/bin/sh\nprintf %s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"structcorpus-release","load_status":"ok"},{"catalog_id":"limensafe-public-baseline-v0","load_status":"ok"}],"files_skipped_by_reason":{},"directories_skipped":0},"summary":{"findings_total":0},"findings":[]}'"'"'\nexit 0\n' >"$scratch/blind"
chmod +x "$scratch/blind"
refused 'did not block its canary' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/blind"
printf 'notes %s\n' "$term" >"$repo/notes.txt"
git -C "$repo" add -A
git -C "$repo" commit -qm 'add notes'
refused '\[block\] tree' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" reset -q --hard HEAD~1
printf 'notes %s\n' "$term" >"$repo/hidden.txt"
printf 'hidden.txt export-ignore\n' >"$repo/.gitattributes"
git -C "$repo" add -A
git -C "$repo" commit -qm 'add hidden notes'
refused '\[block\] tree' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" reset -q --hard HEAD~1
for ignore_file in .gitignore .limensafeignore; do
  printf 'notes %s\n' "$term" >"$repo/leak.txt"
  printf 'leak.txt\n' >"$repo/$ignore_file"
  git -C "$repo" add -f leak.txt "$ignore_file"
  git -C "$repo" commit -qm "add $ignore_file"
  refused '\[block\] tree' ${cat_ok[@]+"${cat_ok[@]}"}
  git -C "$repo" reset -q --hard HEAD~1
done
{
  head -c 11000000 /dev/zero | tr '\0' 'a'
  printf '\nnotes %s\n' "$term"
} >"$repo/big.txt"
git -C "$repo" add big.txt
git -C "$repo" commit -qm 'add a large file'
refused '\[block\] tree' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" reset -q --hard HEAD~1
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"structcorpus-release","load_status":"ok"},{"catalog_id":"limensafe-public-baseline-v0","load_status":"ok"}],"files_skipped_by_reason":{"some_future_reason":1},"directories_skipped":0},"summary":{"findings_total":1},"findings":[{"decision":"block","replacement_id":"StructcorpusCanary","severity":"high"}]}'"'"'\nexit 1\n' >"$scratch/skipper"
chmod +x "$scratch/skipper"
refused 'files were skipped, not scanned: some_future_reason=1' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/skipper"
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"structcorpus-release","load_status":"ok"},{"catalog_id":"limensafe-public-baseline-v0","load_status":"ok"}],"files_skipped_by_reason":{},"directories_skipped":2},"summary":{"findings_total":1},"findings":[{"decision":"block","replacement_id":"StructcorpusCanary","severity":"high"}]}'"'"'\nexit 1\n' >"$scratch/dirskipper"
chmod +x "$scratch/dirskipper"
refused 'directories were skipped' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/dirskipper"
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"structcorpus-release","load_status":"ok"},{"catalog_id":"limensafe-public-baseline-v0","load_status":"ok"}]},"summary":{"findings_total":1},"findings":[{"decision":"block","replacement_id":"StructcorpusCanary","severity":"high"}]}'"'"'\nexit 1\n' >"$scratch/noaccount"
chmod +x "$scratch/noaccount"
refused 'does not account for skipped files' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/noaccount"
printf 'bin\0ary\n' >"$repo/blob.bin"
git -C "$repo" add blob.bin
git -C "$repo" commit -qm 'add a binary'
passes ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" reset -q --hard HEAD~1
link_oid="$(printf '%s' "/opt/$term/x" | git -C "$repo" hash-object -w --stdin)"
git -C "$repo" update-index --add --cacheinfo "120000,$link_oid,link"
git -C "$repo" commit -qm 'add link'
refused '\[block\] tree' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" reset -q --hard HEAD~1
printf 'notes %s\n' "$term" >"$repo/notes.txt"
git -C "$repo" add -A
git -C "$repo" commit -qm 'add notes'
printf 'scrubbed\n' >"$repo/notes.txt"
refused '\[block\] tree' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" checkout -q -- notes.txt
git -C "$repo" reset -q --hard HEAD~1
printf 'more\n' >"$repo/more.txt"
git -C "$repo" add -A
git -C "$repo" commit -qm "mention $term"
refused '\[block\] commit' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" reset -q --hard HEAD~1
printf 'Title\n\nBody about %s\n' "$term" >"$scratch/pr.md"
refused '\[block\] pr text' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_PR_TEXT="$scratch/pr.md"
printf 'Title\n\nclean body\n' >"$scratch/pr-clean.md"
passes ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_PR_TEXT="$scratch/pr-clean.md"
grep -q 'pr text' "$scratch/out"
: >"$scratch/pr-empty.md"
refused 'non-empty file' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_PR_TEXT="$scratch/pr-empty.md"
git -C "$repo" switch -q -c "topic-$term"
refused '\[block\] branch name' ${cat_ok[@]+"${cat_ok[@]}"}
git -C "$repo" switch -q feature
refused 'STRUCTCORPUS_SURFACE_PR_TEXT is required' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1
passes ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1 STRUCTCORPUS_SURFACE_PR_TEXT="$scratch/pr-clean.md"
passes ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1 STRUCTCORPUS_SURFACE_SCOPE=release
refused 'STRUCTCORPUS_SURFACE_RELEASE_BASE override is not permitted' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_SCOPE=release STRUCTCORPUS_SURFACE_RELEASE_BASE=HEAD
refused 'base no-such-ref not found' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_BASE=no-such-ref
# The catalog-backed scan also requires the built-in baseline to load.
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"structcorpus-release","load_status":"ok"}],"files_skipped_by_reason":{},"directories_skipped":0},"summary":{"findings_total":1},"findings":[{"decision":"block","replacement_id":"StructcorpusCanary","severity":"high"}]}'"'"'\nexit 1\n' >"$scratch/nobaseline"
chmod +x "$scratch/nobaseline"
refused 'catalog limensafe-public-baseline-v0 did not load' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_LIMENSAFE_BIN="$scratch/nobaseline"
refused 'STRUCTCORPUS_SURFACE_SCOPE must be pr or release' ${cat_ok[@]+"${cat_ok[@]}"} STRUCTCORPUS_SURFACE_SCOPE=Release

# Baseline-only (CI) mode: no catalog, built-in sentinel on every surface.
bl=(STRUCTCORPUS_SURFACE_BASELINE_ONLY=1)
passes "${bl[@]}"
grep -q '\[ok\] baseline blocks its sentinel' "$scratch/out"
refused 'requires LIMENSAFE_CATALOG_PATH to be unset' "${bl[@]}" ${cat_ok[@]+"${cat_ok[@]}"}
refused 'requires LIMENSAFE_CATALOG_PATH to be unset' "${bl[@]}" LIMENSAFE_CATALOG_PATH=
refused 'cannot satisfy STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1' "${bl[@]}" STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1
refused 'baseline-only scan is PR scope only' "${bl[@]}" STRUCTCORPUS_SURFACE_SCOPE=release
refused 'STRUCTCORPUS_SURFACE_BASELINE_ONLY must be 0 or 1' STRUCTCORPUS_SURFACE_BASELINE_ONLY=yes
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"limensafe-public-baseline-v0","load_status":"ok"}],"files_skipped_by_reason":{},"directories_skipped":0},"summary":{"findings_total":0},"findings":[]}'"'"'\nexit 0\n' >"$scratch/blindbaseline"
chmod +x "$scratch/blindbaseline"
refused 'the baseline did not block its sentinel' "${bl[@]}" STRUCTCORPUS_LIMENSAFE_BIN="$scratch/blindbaseline"
printf '#!/bin/sh\nprintf %%s '"'"'{"scan_metadata":{"catalogs_loaded":[{"catalog_id":"limensafe-public-baseline-v0","load_status":"missing_error"}],"files_skipped_by_reason":{},"directories_skipped":0},"summary":{"findings_total":1},"findings":[{"decision":"block","severity":"high"}]}'"'"'\nexit 1\n' >"$scratch/nobaseline2"
chmod +x "$scratch/nobaseline2"
refused 'catalog limensafe-public-baseline-v0 did not load' "${bl[@]}" STRUCTCORPUS_LIMENSAFE_BIN="$scratch/nobaseline2"
printf 'notes %s\n' "$sentinel" >"$repo/notes.txt"
git -C "$repo" add -A
git -C "$repo" commit -qm 'add notes'
refused '\[block\] tree' "${bl[@]}"
git -C "$repo" reset -q --hard HEAD~1
printf 'more\n' >"$repo/more.txt"
git -C "$repo" add -A
git -C "$repo" commit -qm "mention $sentinel"
refused '\[block\] commit' "${bl[@]}"
git -C "$repo" reset -q --hard HEAD~1
printf 'Title\n\nBody %s\n' "$sentinel" >"$scratch/pr-sentinel.md"
refused '\[block\] pr text' "${bl[@]}" STRUCTCORPUS_SURFACE_PR_TEXT="$scratch/pr-sentinel.md"
passes "${bl[@]}" STRUCTCORPUS_SURFACE_PR_TEXT="$scratch/pr-clean.md"
git -C "$repo" switch -q --detach
refused '\[block\] branch name' "${bl[@]}" STRUCTCORPUS_SURFACE_BRANCH_NAME="topic-$sentinel"
passes "${bl[@]}" STRUCTCORPUS_SURFACE_BRANCH_NAME=topic-clean
grep -q '\[ok\] branch name' "$scratch/out"
git -C "$repo" switch -q feature

[[ "$(uname -s)" != Darwin || "${case_checked:-0}" == 1 ]] || {
  echo 'error: the case-alias controls did not run on macOS' >&2
  exit 1
}
echo '[ok] surface-scan: catalog location (path, case incl. numeric names, .., hard link), canary and vocabulary, scanner errors, each surface incl. export-ignore, ignore files, oversize files, symlinks and local edits, skip accounting, required PR text, baseline-only mode'
