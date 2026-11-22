---
Record: DDR-0014
Title: Per-format manifest layout and the format registry
Status: Proposed
Date: 2026-11-22
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0014: Per-format manifest layout and the format registry

## Context

`fixtures/`, `recipes/`, and `generators/` already hold one subdirectory per
format. The case manifest, profiles, span conventions, and upstream lock sat
directly under `manifests/`, so a second format would have shared one flat
registry with YAML. Identifiers, revisions, input bytes, generated case IDs,
recipe digests, and hydrated paths must not change when storage moves.

## Decision

1. **Per-format registries.** Each format keeps its own static case shard,
   profiles, span conventions, and upstream lock under `manifests/<format>/`:

   ```text
   manifests/
     formats.json                   format registry (formats/v1)
     cases.jsonl                    generated aggregate of every static case shard
     yaml/
       cases.jsonl                  YAML static cases (authoritative)
       profiles/<id>.r<N>.json
       span-conventions/<id>.r<N>.json
       upstreams.lock.json
   fixtures/yaml/  recipes/yaml/  generators/yaml/
   ```

   The bytes of every moved file are unchanged. DDR-0003 and DDR-0004 still
   define the records; only their storage paths move.
2. **The format registry.** `manifests/formats.json` (schema
   `schemas/formats.v1.schema.json`) is the one hand-edited cross-format
   index. Each entry declares:
   - `status`, which is always `active`;
   - its `dialects`;
   - `generated_input_extension`, the suffix of hydrated generated inputs; and
   - the paths of the inventories it has: `cases`, `profiles`,
     `span_conventions`, `upstreams`, `fixtures`, `recipes`, and `generators`.

   Each inventory has one allowed path: `manifests/<format>/cases.jsonl`,
   `manifests/<format>/profiles`, `manifests/<format>/span-conventions`,
   `manifests/<format>/upstreams.lock.json`, `fixtures/<format>`,
   `recipes/<format>`, and `generators/<format>`. Tools read every path from
   the registry.
3. **Only implemented formats are accepted.** The tool lists the formats it
   implements, with their dialects, required inventories, and generated-input
   extension. Today that is YAML only. An entry for any other format is
   refused even when it says `active`, because activation needs that format's
   own schemas, validation, and decision record. Unknown members, unknown
   `schema_version` values, and duplicate JSON keys are refused. There are no
   reserved entries.
4. **Inventories are declared, not assumed.** Every declared path must exist
   and be non-empty. A format declares at least one of `cases` or `recipes`.
   `recipes`, `generators`, and `generated_input_extension` come together, and
   `fixtures` requires `cases`. There is no rule that every format has static
   cases, recipes, and profiles. YAML declares all seven inventories.
5. **Paths are checked.** A declared path must be a normalized
   repository-relative path at its allowed location. It may not traverse,
   pass through a symbolic link, resolve outside the repository, name the
   root aggregate or the registry, or overlap another declared path in the
   same or another format. Under `fixtures/`, `recipes/`, `generators/`, and
   `manifests/`, every entry must be declared by an active format, apart from
   `manifests/formats.json` and `manifests/cases.jsonl`. Each case record's
   `format` matches its shard, and each recipe's `format` matches its recipe
   directory. Case, recipe, and profile dialects are declared for that format.
   Profiles and span conventions resolve only within the record's own format.
6. **One static index.** `manifests/cases.jsonl` is the concatenation of each
   format's static case shard. Shards are taken in sorted format-id order, and
   each keeps its own byte and line order, with LF line endings. With YAML as
   the only format, it is byte-identical to `manifests/yaml/cases.jsonl`. It
   holds static cases only; generated cases stay in the hydrated manifest
   (DDR-0004). `corpus.py validate` regenerates the aggregate in memory and
   fails on a stale or missing one, without writing. `corpus.py aggregate`
   (`make aggregate`) is the only command that writes it.
7. **One case-id namespace.** Static case IDs are unique across all shards.
   A generated ID is `<recipe id>.<local id>`. Recipe IDs are unique across
   all formats, and no recipe ID may be a dot-separated prefix of another. No
   static ID may lie inside a recipe's generated prefix. `hydrate` also
   refuses a generated ID that equals a static ID or is produced twice.
8. **Generated inputs.** `hydrate`, `verify`, and the bounded runner build the
   hydrated input path from the registry's `generated_input_extension`. For
   YAML that is `inputs/yaml/<recipe id>/<local id>.yaml`, as before. The
   suffix is never used to infer a format, encoding, dialect, or expected
   result. Static inputs resolve through their recorded `input.path` and
   hashes.

## Consequences

- Case and recipe identities, revisions, expectations, review states, input
  bytes, recipe digests, and hydrated output are unchanged. The existing case,
  recipe, profile, span-convention, and upstream-lock schemas are unchanged.
- Readers that use `manifests/cases.jsonl` and hydration keep working
  unchanged. Readers of profiles, span conventions, or the upstream lock take
  those paths from `manifests/formats.json` when they move to a pin that
  includes this layout. Earlier pins keep their earlier paths.
- Adding a format needs its own schemas, tool support, and decision record
  before its registry entry is accepted.
