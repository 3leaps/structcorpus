---
Record: DDR-0009
Title: Resource ladders, configured limit errors, and running hazardous cases
Status: Proposed
Date: 2026-10-15
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0009: Resource ladders, configured limit errors, and running hazardous cases

## Context

The adversarial families for alias expansion, many keys, late failure, and
depth need two kinds of material:

- **Exact limit boundaries:** small inputs one below, at, and one above a
  limit, where the specification's arithmetic decides the outcome.
- **Stress ladders:** geometrically larger inputs that exercise time and
  memory. Their outcome under default limits depends on budgets the corpus does
  not fix, so it is measured, not expected (DDR-0002).

The yamlprims specification revision 1.3 says load-limit boundaries are tested
with named configured values. It also leaves the counting of load depth
(lexical and materialized nesting, and alias height) as an open validation
item.

## Decision

1. **Limit errors may name `configured`,** an integer that must equal the value
   of the named limit in the expectation's profile. It is allowed only on
   `limit` errors, requires a profile with explicit `limits`, and is checked
   twice: by `validate` for committed cases, and while generating recipes, so
   a wrong value fails hydration.
2. **Generators may yield format-level events** as an optional sixth element,
   and may yield no value expectation. A generated case carries any non-empty
   subset of `events` and `value`, as committed cases already may. Generators
   that yield five elements produce unchanged records and digests.
3. **Boundary recipe.** `resource-boundaries` (smoke tier, `yamlprims-core-limits`
   r2) covers `max_alias_events`, `max_expanded_nodes`, `max_mapping_entries`,
   and `max_nodes`. Each set of three inputs is built so that only the named
   measure moves across the limit and every other limit holds. That property is
   asserted by the generator, and an independent event-order model checks it.
   An alias is checked before its copy (section 5.4).
4. **Stress ladders,** all stress tier, hazardous, with the SecDR-0002 default
   budgets:

   | Ladder | Range | Expectations |
   | --- | --- | --- |
   | alias fan-out | 10 to 10,000 aliases | events |
   | nested fan-out | doubling per level, 3 to 15 levels | events |
   | many keys | 10 to 100,000 keys | events, and a duplicate-key error for the variant with a repeated key |
   | late failure | 1,024 to 262,144 valid entries | a syntax or duplicate-key error |
   | depth | 8 to 1,024 nested sequences | events only |

   An expected error in a stress ladder must be the first error. The
   specification's limits are proposed defaults, so a ladder that expects an
   error is bound to **`yamlprims-core-stress` r1**: `yamlprims-core` r3 with
   explicit limits large enough to reach each defect. Those are the proposed
   defaults, except `max_nodes` (1,048,576) and `max_mapping_entries`
   (524,288).

   For every row that expects an error, the generator recounts the measures as
   built, through the defect, and refuses any row where another limit would be
   reached first. That covers input bytes, nodes, mapping entries, owned bytes,
   and scalar and key bytes. A syntax error is outranked only by the input gate
   (section 7.1). A recipe may pass a profile limit to its generator as
   `limit_<field>`, and generation fails unless it equals the profile's value.
   Ladders with events only stay under `yamlprims-core` r3: format events are
   bound to no profile.
5. **Depth carries no limit expectation** until the specification defines
   how load depth is counted. Depth boundaries are added as a new recipe once
   it does.
6. **`runner.py run`** executes a hydrated tier's cases, by default only
   hazardous ones, through a caller-supplied image and command, one container
   per case with that case's budgets:
   - the hydrated root is verified first, and nothing runs if verification
     fails;
   - each result records the outcome, the exit code, the memory-limit flag,
     the elapsed time, and the length and sha256 of standard output, never the
     output itself;
   - each result also records the limits that were enforced, the enforcement
     mechanism, and `peak_memory: not_measured`. Memory is bounded, and an
     out-of-memory kill is observed, but peak use is not measured;
   - comparing output with expectations is the consumer driver's job;
   - an unavailable runtime reports every selected case as `blocked`.

## Consequences

- Consumers get limit boundaries and stress-ladder errors that do not depend on
  the specification's proposed defaults, and stress inputs that are bounded when
  run.
- A `run` result records execution, not conformance: `pass` means the command
  completed within its budgets. It is not a comparison with expected values,
  and it is not qualification evidence.
- `max_input_bytes`, `max_documents`, `max_output_bytes`, and `max_warnings`
  are not load-error boundaries here, because the specification tests them
  through the input gate, stream entrypoints, encoders, and M3, respectively.
- Depth limits are the visible gap, recorded in `docs/coverage.md`.
