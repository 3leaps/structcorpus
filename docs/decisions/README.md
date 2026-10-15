# Decision records

structcorpus records decisions using the `*DR` family defined in
[3leaps/crucible ADR-0003](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/docs/decisions/ADR-0003-decision-record-taxonomy.md)
and its [normative catalog](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/docs/repository/decision-records.md).

- **Naming:** `<TYPE>-<NNNN>-<kebab-slug>.md`. Numbers are four digits,
  monotonic per type across the whole repository, and never reused.
- **Types:** ADR (architecture), DDR (design/data), SecDR (security posture),
  PDR (process), EPR (principle).
- **Lifecycle:** `Proposed` → `Accepted` → `Superseded` / `Rejected` /
  `Withdrawn`. Accepted decisions are superseded, never rewritten. A record
  drafted by an implementer stays `Proposed` until the maintainer accepts it.
- **Location:** this repository files every type under `docs/decisions/`.
  That is a local choice, not a crucible requirement.
- **SecDRs here are public.** They describe controls and posture, never
  defects or exploit paths.

| Record | Title | Status |
| --- | --- | --- |
| [ADR-0001](ADR-0001-engine-neutral-corpus-scope.md) | Engine-neutral corpus scope and consumer boundary | Proposed |
| [ADR-0002](ADR-0002-python-stdlib-tooling.md) | Python 3 standard library for corpus tooling and generators | Proposed |
| [DDR-0001](DDR-0001-byte-exact-fixture-storage.md) | Byte-exact fixture storage, size guardrails, and portable names | Proposed |
| [DDR-0002](DDR-0002-format-events-and-profile-expectations.md) | Format-level events separate from profile-bound expectations | Proposed |
| [DDR-0003](DDR-0003-case-record-and-value-notation.md) | Case record, value notation, and span convention r1 | Proposed |
| [DDR-0004](DDR-0004-recipes-and-hydration.md) | Generator recipes, pinned digests, and bounded hydration | Proposed |
| [DDR-0005](DDR-0005-typed-conversion-expectations.md) | Typed-conversion expectations | Proposed |
| [DDR-0006](DDR-0006-profile-revisions-for-spec-1-1.md) | Profile and span-convention revisions for yamlprims specification 1.1 | Proposed |
| [DDR-0007](DDR-0007-limits-profiles-and-stress-recipes.md) | Explicit-limits profiles, recipe hazards and budgets, and listing | Proposed |
| [DDR-0008](DDR-0008-node-spans-and-spec-1-3-profiles.md) | Node spans and profile revisions for yamlprims specification 1.3 | Proposed |
| [SecDR-0001](SecDR-0001-public-only-admission.md) | Public-only admission and classification compliance | Proposed |
| [SecDR-0002](SecDR-0002-bounded-execution-containment.md) | Bounded execution and memory containment for hostile cases | Proposed |
| [PDR-0001](PDR-0001-staged-releases.md) | Staged releases, each with its own acceptance list | Proposed |
| [PDR-0002](PDR-0002-goneat-maintainer-toolchain.md) | goneat as the maintainer format, lint, and schema toolchain | Proposed |

Reviewers: any change that adds or modifies a case is checked against
SecDR-0001. Any change to execution tooling is checked against SecDR-0002.
