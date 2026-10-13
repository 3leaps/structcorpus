---
Record: DDR-0001
Title: Byte-exact fixture storage, size guardrails, and portable names
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0001: Byte-exact fixture storage, size guardrails, and portable names

## Context

Parser behavior depends on exact bytes: BOMs, CRLF versus LF, trailing
whitespace, tabs, invalid UTF-8, NUL. Git newline conversion, editor
settings, and formatters all rewrite those bytes silently. Consumers check
out on Linux, macOS, and Windows and must see identical bytes. Git is also
a poor place to store large repetitive inputs.

## Decision

1. **Byte preservation.** `fixtures/` and `expected/` are marked `-text` in
   `.gitattributes`, so Git never converts line endings or applies text
   filters there. Formatters and linters are configured to exclude both
   trees. A fixture's hash and length are computed over its on-disk bytes and
   rechecked after checkout.
2. **Binary inputs are allowed.** Inputs containing invalid UTF-8 or NUL use
   the `.bin` extension. Documentation shows them as bounded escaped previews,
   never raw.
3. **Size guardrails for committed material:** at most 256 KiB per fixture
   file, and at most 32 MiB in total across `fixtures/` and `expected/`.
   Exceptions need a recorded reason and review. These limits are about Git
   storage, not about parser input limits.
4. **Generate rather than commit large inputs.** Repetitive or large inputs,
   and exhaustive truth tables, come from reviewed generators. Their recipes
   pin output hashes and counts. Hand-checked boundary rows are committed as
   goldens next to them. If a regression depends on exact bytes, the
   minimized bytes are committed, not regenerated.
5. **Portable names.** Case IDs and committed paths:
   - use lowercase ASCII `[a-z0-9._-]`, starting with a letter or digit;
   - are unique when compared case-insensitively;
   - avoid Windows reserved device names (`con`, `prn`, `aux`, `nul`,
     `com1`–`com9`, `lpt1`–`lpt9`) as any path component stem;
   - have no trailing dot or space;
   - are at most 100 characters per ID and 200 per repository-relative path.
6. **No Git LFS.** Large, irreducible public specimens are distributed as
   immutable release artifacts, with compressed and uncompressed hashes and
   lengths, provenance, and notices. Extraction is bounded in total size and
   file count, and it rejects path traversal, absolute paths, links, and
   special files before writing anything.

## Consequences

- Fixture files need not be "nice" text, and tooling must never normalize
  them.
- Some useful large truth tables live only as generator, recipe, and hash,
  and are regenerated before use.
- Linux, macOS, and Windows parity becomes a mechanical hash check. A
  platform that has not been tested is reported as unrun, not as passing.
- The naming rule rejects some descriptive IDs, and the validator enforces it.
