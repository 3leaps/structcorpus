---
Record: ADR-0001
Title: Engine-neutral corpus scope and consumer boundary
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
---

# ADR-0001: Engine-neutral corpus scope and consumer boundary

## Context

Structured-document readers (YAML, JSON, XML, and their language bindings)
need test material that is reviewed independently of any one implementation.
That material should be reusable across engines and bindings, and it should
keep large or hazardous workloads out of ordinary unit-test suites. YAML is the
first format. Consumers include native libraries and their bindings in
other languages.

Inside a single implementation's repository, two things go wrong. The tests
drift toward whatever that engine already does, and expectations get worded
in that engine's API terms.

## Decision

1. **The corpus owns** inputs, expected properties, provenance, generators,
   recipes, schemas, and the manifest contract. **Consumers own** the drivers
   that run their real APIs against the corpus, along with their own small
   mandatory regression tests.
2. **No parser is imported or built here.** Corpus tooling never depends on a
   candidate engine, and checking corpus metadata never requires the YAML
   engine under test. Metadata is JSON/JSONL.
3. **Hydration prepares inputs and never runs a candidate parser.** Any
   execution runner shipped here is a separate, minimal, bounded tool.
4. **Expectations are pinned to a profile.** Format-level facts (whether the
   input is valid in a named format revision, and the event structure it
   produces) are kept apart from adapter policy (scalar resolution schema,
   merge-key handling, duplicate-key equality, numeric conversion, limits and
   resource accounting). Policy expectations exist only under a named,
   versioned profile. When several engines agree, that is an observation, not
   an oracle, and observed engine behavior is recorded in results, never
   promoted to expected truth.
5. **Formats are added when a consumer exists.** `yaml` is implemented. The
   `json` and `xml` namespaces are reserved. The formats share metadata
   conventions, not a universal value tree, and equivalence across formats is
   never assumed.
6. **Releases are pinned, not tracked.** Consumers pin a corpus commit or
   immutable release plus content hashes and a profile revision. This
   repository does not track, enumerate, or pin its consumers.

## Consequences

- The case schema has to express "valid YAML 1.2.2, events X" separately from
  "under profile P, value Y or error category Z". DDR-0002 covers this.
- A consumer can disagree with a policy profile by defining its own profile
  without disputing format-level truth.
- The corpus is more work up front than tests kept in a consumer repo. The
  justification is independent review and reuse, and the first consumer's
  integration should demonstrate both before the format count grows.
- Running a separate repository does not isolate execution. Hazardous cases
  still need the containment rules recorded in a separate security decision.
