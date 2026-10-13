---
Record: SecDR-0001
Title: Public-only admission and classification compliance
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
Audience: public
---

# SecDR-0001: Public-only admission and classification compliance

## Context

structcorpus is a public test corpus for structured-document readers
(YAML first; JSON and XML reserved). Fixtures that are interesting to parser
authors tend to resemble real configuration: deployment manifests, CI files,
application settings. The easiest way to get such a file is to take a real one
and edit it, and that is the path this record closes.

The 3 Leaps classifier standards are published in
[3leaps/crucible](https://github.com/3leaps/crucible). This corpus is pinned to
commit `fc6c49a3a1dd171895fc8d8b8c458f33692eb033`:

- [Classifiers framework](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/docs/standards/classifiers-framework.md)
- [Data sensitivity standard](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/docs/standards/data-sensitivity-classification.md)
  and its [dimension definition](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/config/classifiers/dimensions/sensitivity.dimension.json)
- [Access-tier standard](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/docs/standards/access-tier-classification.md)
  and its [dimension definition](https://github.com/3leaps/crucible/blob/fc6c49a3a1dd171895fc8d8b8c458f33692eb033/config/classifiers/dimensions/access-tier.dimension.json)

Those standards classify blinded data (`2-blinded`: obfuscated real data,
"test data with real structure but fake identities") as distinct from public
data (`0-public`). Renaming hosts, keys, or people in a real file produces
blinded data, not public data.

## Decision

**Only `0-public` material is admitted. Blinded, redacted, obfuscated, or
otherwise derived-from-private material is never admitted, at any level of
transformation.**

1. **Exact classifier values.** Every case record carries
   `classifiers.sensitivity: "0-public"` and `classifiers.access-tier: "public"`.
   These are compared as exact strings against the pinned dimension
   definitions. Synonyms (`public`, `open`) and ordering comparisons are not
   accepted. A missing classifier, `unknown`, or any other value fails
   validation.
2. **Two admissible origins, recorded separately from classification:**
   - *synthetic*: independently constructed for public release, from the
     format specification or first principles, with no structure, identifiers,
     content, or secrets derived from private material;
   - *public-source*: material from a pinned public upstream with documented
     redistribution rights, retained license and notice, and review that it
     carries no personal or secret content. Being publicly reachable is not by
     itself evidence of classification or permission.
3. **Explicitly excluded**, even with names replaced: redacted production
   files, obfuscated customer or partner documents, private configuration
   templates, copied private incident reports or research notes, and any
   output of a blinding process. When a private file shows an interesting
   behavior, the behavior is recreated from scratch as a minimal synthetic
   case. The private file is not edited down.
4. **No intake staging in this repository.** There is no `unknown/`,
   `pending/`, or quarantine directory. Unclassified submissions are either
   classified outside the public checkout or declined.
5. **Reserved identifiers only.** Hostnames use reserved names such as
   `example.invalid`, `example.com`, or `.test`. Addresses come from
   documentation ranges (RFC 5737, RFC 3849). No real credentials, keys,
   customer identifiers, or production endpoints appear. If a key-like payload
   is ever required, it comes from a pinned release of
   [3leaps/synthcorpus](https://github.com/3leaps/synthcorpus) with its
   notices.
6. **The rule covers every committed byte**, not just fixture bodies. It
   applies to manifests, filenames, case IDs, comments, expected values,
   recipes, reports, release archives, and generated outputs. Run results
   published from this repository are stripped of host paths and environment
   metadata.
7. **Provenance never points at non-public places.** A synthetic case
   records its origin generically (`synthetic`, authored for structcorpus)
   with an authoring method. Provenance, comments, generator source, and
   commit text never name non-public repositories, branches, commit hashes,
   internal review lanes, or products. Material migrated from earlier
   non-public work is admitted only if it is itself synthetic, and its
   metadata and code comments are rewritten to meet this rule before the
   first commit that contains it.
8. **Dependency direction is one way.** Consumers pin structcorpus. This
   repository never pins, depends on, or keeps an inventory of its
   consumers, and never references private material of any kind.
   **One exception:** a profile may cite the *published normative
   specification* that defines it (DDR-0002), by public URL and revision
   or errata identifier. That citation identifies the rules being tested.
   It does not list who consumes the corpus.
9. **A scan is not a classification.** Secret and leak scanners run as
   defense in depth. A clean scan does not substitute for provenance review,
   and a provenance record is required regardless of scan results.

## Consequences

- Contributors cannot submit "a real-world file that broke my parser". They
  submit a minimized synthetic reproduction instead. This costs some realism,
  which is accepted: parser behavior depends on syntax and structure, both of
  which can be built from the specification.
- The repository is public from its first commit, so there is no private
  period in which to clean up. Every commit, including the first, meets this
  record.
- The validator enforces items 1, 2, and 4 mechanically. Negative tests must
  show it rejects a missing classifier, `unknown`, a non-public value, a
  synonym in place of the exact key, and a case with no provenance.
- Items 3, 5, 6, 7, and 8 depend on review. **devrev and secrev check every change
  that adds or modifies a case** for derived-from-private content, including
  structural fingerprints. A case whose shape mirrors a specific non-public
  system is rejected even if every literal value is synthetic.
- Classification is independent of execution hazard. A public alias-expansion
  bomb is `0-public` and still requires bounded execution. Execution
  containment is a separate decision.
- If a classifier definition is ever vendored into this repository, the
  matching meta-schema is vendored with it, along with the source commit and
  notices, as the classifiers framework requires.
- Moving the crucible pin is a reviewed change. It must state whether the
  `0-public` or `public` definitions changed.
