---
Record: DDR-0003
Title: Case record, value notation, and span convention r1
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0003: Case record, value notation, and span convention r1

## Context

DDR-0002 splits expectations into `events`, `value`, and `locations`. This
record fixes the concrete shape of each, so that schemas, validators, and
consumer drivers agree. The value notation has to be JSON (ADR-0002) and
must not lose information a YAML value carries: entry order, non-string
keys, tags, exact integers, float bit patterns, negative zero, and
non-finite values.

## Decision

### Case record (`case/v1`)

`manifests/cases.jsonl` holds one case per line. Required members:
`schema_version`, `id`, `revision`, `format`, `dialect`, `category`,
`classifiers`, `provenance`, `input`, `expectations`, `execution`,
`review`. `relations` is optional. `schemas/case.v1.schema.json` defines
the structure; `tools/corpus.py validate` also checks cross-references,
hashes, and lengths.

- `input` has exactly one of `path` (a committed file under
  `fixtures/<format>/`) or `recipe` (a reference to a reviewed generator
  recipe), plus `sha256` and `bytes` of the actual uncompressed input.
- `expectations` carries one or more layers. `events` has a `status`
  (`valid` or `invalid`) and, for valid input, an `events` list in the pinned
  event notation. `value` is a list of profile-bound entries, each naming a
  profile and its revision. `locations` names a span convention and its
  revision, plus a list of located events.
- An `id` is never reused. A changed expectation increments `revision` in a
  new commit; old revisions remain reproducible from history.

### Event notation

The notation is the yaml-test-suite event format at the pinned upstream
revision recorded in `manifests/upstreams.lock.json`. Each event is one
string, for example `+MAP`, `=VAL :a`, `=VAL &x 'b`, `=ALI *x`. Event
strings carry no positions.

### Value notation (`yaml-value/1`)

A value is a JSON object with a `t` member:

| `t` | Members | Meaning |
| --- | --- | --- |
| `null` | — | null |
| `bool` | `v`: `true`/`false` | boolean |
| `int` | `v`: decimal string, optional leading `-` | exact integer of any size |
| `float` | `bits`: 16 lowercase hex digits | IEEE 754 binary64 bit pattern (sign of zero, NaN, and infinities are exact) |
| `str` | `v`: string | string |
| `seq` | `items`: array of values | sequence |
| `map` | `entries`: array of `[key, value]` pairs | mapping; order preserved; keys are any value |
| `tagged` | `tag`: string, `inner`: value | value carrying an explicit non-core tag |

Errors use `{"error": {"phase": <DDR-0002 phase>}}`. A `limit` name is
required for the `limit` phase. `kind` (snake_case) is optional; when
present it is normative under the case's profile. Engines name errors
differently, so phase is the portable part. Messages are never normative.

Integers are strings because the metadata subset (ADR-0002) allows only
integers within ±(2^53 − 1).

### Profiles (`profile/v1`)

`manifests/profiles/<id>.r<N>.json` declares a profile's `id`, `revision`,
`dialect`, scalar schema, policy choices, and `cites`. `cites` lists only
published normative specifications, by URL and revision. A value
expectation that names an undeclared profile or revision fails validation.

### Span convention r1 (`span-convention/v1`)

Offsets are zero-based UTF-8 byte offsets into the input, with half-open
`[start, end)` spans. Revision 1 defines:

- **scalar** (`=VAL`): `start` at the first byte of the scalar's text,
  including any opening quote or block indicator, and excluding properties
  (anchor and tag); `end` after the last byte of that text, including a
  closing quote;
- **alias** (`=ALI`): from the `*` through the end of the alias name.

Collection, document, and stream events, and the extent of properties, are
deliberately undefined in r1. A location expectation for an undefined kind
fails validation. It is not guessed.

## Consequences

- Any engine can map its events and values onto this notation without
  adopting another adapter's representation.
- Consumers convert integers from strings, which costs a little and stays
  exact.
- Span coverage starts narrow. Defining more node kinds requires a new
  convention revision, so existing expectations never change meaning.
