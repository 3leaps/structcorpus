---
Record: DDR-0013
Title: Profile revisions for yamlprims specification 1.5
Status: Proposed
Date: 2026-11-11
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0013: Profile revisions for yamlprims specification 1.5

## Context

The yamlprims specification moved from revision 1.4 (`spec-v1.4`) to revision
1.5 (`spec-v1.5`), recording four errata items in section 16:

- **1.5/E-1 (§3, §4.4, §7.1, §11.1, §13.2).** Adds checked caller-tree
  constructors (`Document::new`, `Document::with_metadata`, `Tag::try_new`,
  `Tag::with_spelling`, and `Tagged::new`), clarifies section 4.4's existing
  `!!merge` collection, scalar, and key behavior without changing historical
  profile expectations, specifies iterative heap-stack `Drop`, `Clone`, and
  `PartialEq` and bounded `Debug` plus crate traversals, incorporates the
  closed 81-code `SyntaxKind` catalog, and defines symmetric `decode_wire`
  validation across all four bindings.
- **1.5/E-2 (§8.2, §10.2, §13.2, §14).** Specifies the deterministic 2-space
  block-first YAML 1.2.2 Core emitter (`emit`, `emit_all`, `EmitOptions`, and
  `EmitLimits`), mapping-key and literal-block selection rules, RFC 3986
  section 3.3 verbatim tag escaping, `CompatQuoting::Yaml11Safe` default
  quoting, `serde::Serialize` (`to_node`, `to_string`, and `to_string_with`),
  CLI `emit`, and four-language byte-for-byte emitter parity.
- **1.5/E-3 (§10.1, §11.6, §13.2).** Specifies the six-rule RFC 7493 I-JSON
  projection (`encode_ijson`, `load_ijson`, `load_ijson_bytes`,
  `Options::ijson_default()`, CLI `dump --ijson`, and host equivalents) with
  section 7.1 source-validation precedence before Phase 5 document-cardinality
  checks, closed-set `ErrorKind` diagnostics, normative `Type` strings, and
  RFC 8785 number and string token formatting.
- **1.5/E-4 (§1, §2, §11.2, §11.5).** Aligns the multi-language architecture
  sections across the pure-Go twin, zero-import `wasm32` TypeScript, and
  `PyO3` `abi3-py310` Python bindings.

The retained source-loader policy fields (`duplicate_keys`, `merge_keys`,
`integer_range`, `documents`, `unknown_tags`, and `flow_indentation`), wire
grammar version 1 (`yamlprims-value/1`), and the section 6 subtree-weight
formula are unchanged from revision 1.4. Caller-constructed value trees, wire
decoding, YAML emission, `serde::Serialize`, and I-JSON projection stay outside
this corpus (ADR-0001).

## Decision

1. **Earlier profiles stay byte-for-byte.** Every profile that cites
   `spec-v1.4` or an earlier tag keeps its citation, limits, and recipes.
   A specification change is a new profile revision.
2. **Revision 5 policy profiles cite `spec-v1.5`** by tag, commit, and the
   sha256 of `docs/spec/yamlprims-spec.md`:
   - `yamlprims-core` r5, `yamlprims-core-merge-apply` r5, and
     `yamlprims-core-merge-as-key` r5 model single-document entrypoints;
   - `yamlprims-core-stream` r5 models multi-document entrypoints.

   Their retained source-loader policy fields match the revision 4 profile of
   the same id. They carry no cases in this record. A later source-loader
   recipe that wants default options under revision 1.5 cites r5 without
   retargeting an r4 recipe.
3. **Caller-tree, wire-decoder, emitter, Serde, and I-JSON surfaces stay
   outside the corpus.** Those surfaces either start from an in-memory value
   tree or binary wire buffer, or define output projection and serialization
   that belong in the implementation's own conformance suite rather than in
   this engine-neutral YAML input corpus.

## Consequences

- Consumers pinning specification 1.5 have revision 5 policy profiles citing the
  exact `spec-v1.5` tag, commit, and specification digest.
- Historical pins and revision 1 through 4 profiles and recipes keep their
  bytes and digests unchanged.
- `docs/coverage.md` records the revision 5 policy profiles and keeps the
  remaining revision 1.4 source-loader rows on the planned list.
