# Admission checklist

This is the working checklist for adding or changing a case. The
authoritative rule is
[SecDR-0001](decisions/SecDR-0001-public-only-admission.md).

## Author

- [ ] The material is **synthetic**, built from the format specification or
      from first principles, or it is **public-source** material with a
      pinned upstream, a documented license, and its notices retained.
- [ ] Nothing was derived from private material: no edited real files, no
      redacted or blinded copies, and no structure that mirrors a specific
      non-public system.
- [ ] Hostnames, addresses, and identifiers use reserved forms
      (`example.invalid`, `.test`, RFC 5737/3849 ranges).
- [ ] There are no credentials or key material. If a key-like payload is
      needed, it comes from a pinned public synthcorpus release.
- [ ] `classifiers.sensitivity` is exactly `"0-public"` and
      `classifiers.access-tier` is exactly `"public"`.
- [ ] Provenance is generic for synthetic material. Comments and generator
      source name no non-public repository, branch, commit, product, or
      person.
- [ ] Names follow DDR-0001: lowercase portable names, at most 256 KiB per
      fixture.
- [ ] `python3 tools/corpus.py validate` passes.

## Reviewer (devrev / secrev)

- [ ] The provenance claim is plausible for the content, and is checked
      against the content rather than taken on trust.
- [ ] Filenames, case IDs, manifests, expected values, comments, and commit
      or PR text all meet the rule, not only the fixture body.
- [ ] Every expectation is filed in its proper layer: format-level `events`
      or a named profile (DDR-0002).
- [ ] A hazardous case declares its execution tier and budgets
      (SecDR-0002).

A clean secret or leak scan supports this review but is not classification
evidence by itself.
