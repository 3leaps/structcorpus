#!/usr/bin/env bash
# Full JSON Schema validation of corpus metadata with goneat (ADR-0002).
# Each case line is checked as its own document. Negative controls under
# tests/schema-negative must fail, so a vacuous pass is impossible.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

check() {  # check <schema> <data> <expect: pass|fail>
  if goneat validate data --schema-file "$root/schemas/$1" --data "$2" >"$work/out" 2>&1; then
    got=pass
  else
    got=fail
  fi
  if [ "$got" != "$3" ]; then
    echo "schema-check: $2 against $1: expected $3, got $got" >&2
    cat "$work/out" >&2
    return 1
  fi
}

status=0
n=0
while IFS= read -r line || [ -n "$line" ]; do
  [ -z "$line" ] && continue
  n=$((n + 1))
  printf '%s\n' "$line" >"$work/case-$n.json"
  check case.v1.schema.json "$work/case-$n.json" pass || status=1
done <"$root/manifests/cases.jsonl"
for f in "$root"/manifests/profiles/*.json; do
  check profile.v1.schema.json "$f" pass || status=1
done
for f in "$root"/manifests/span-conventions/*.json; do
  check span-convention.v1.schema.json "$f" pass || status=1
done
check upstreams-lock.v1.schema.json "$root/manifests/upstreams.lock.json" pass || status=1
neg=0
for f in "$root"/tests/schema-negative/*.json; do
  neg=$((neg + 1))
  check "$(basename "$f" | cut -d. -f1).v1.schema.json" "$f" fail || status=1
done
if [ "$n" -eq 0 ] || [ "$neg" -eq 0 ]; then
  echo "schema-check: nothing checked (cases=$n, negatives=$neg)" >&2
  status=1
fi
echo "schema-check: cases=$n negatives=$neg status=$status"
exit "$status"
