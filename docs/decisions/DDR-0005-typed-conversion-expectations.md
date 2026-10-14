---
Record: DDR-0005
Title: Typed-conversion expectations
Status: Proposed
Date: 2026-10-14
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0005: Typed-conversion expectations

## Context

Profiles such as `yamlprims-core` define what happens when a loaded value is
converted into a host type: `"8080"` into a 16-bit integer is a type error,
`70000` is out of range, and a binary32 target rounds to nearest. This is a
separate question from the generic value tree, and engines without a typed API
have nothing to compare against it. It needs its own layer, so that a
generic-only consumer can skip it explicitly and not report it as a mismatch.

## Decision

1. `expectations.typed` is a list of profile-bound entries. Each entry holds:
   - `profile` and `profile_revision`, as for `value`;
   - `path`: the location of the converted node from the document root, as a
     list of string mapping keys and integer sequence indexes. An empty path
     converts the root;
   - `target`, one of: `u8`, `u16`, `u32`, `u64`, `u128`, `i8`, `i16`, `i32`,
     `i64`, `i128`, `f32`, `f64`, `bool`, `string`, `option-bool`;
   - exactly one of `result` (a typed value) or `error` (DDR-0002 phases).
2. **Typed values** reuse the `yaml-value/1` notation (DDR-0003) and add two
   kinds:
   - `{"t": "float32", "bits": "<8 lowercase hex>"}` for a binary32 result;
   - `{"t": "none"}` for an absent `option-bool`.
   Integer targets use `int`, `f64` uses `float`, `bool` uses `bool`, and
   `string` uses `str`.
3. **Error phases.** A conversion failure on a well-formed value is phase
   `typed`, for example kind `type` or `integer_out_of_range`. A value that
   already fails generic loading carries the same error as its `value` layer,
   in the same phase, because conversion never starts.
4. A consumer without a typed API reports this layer as not applicable, never
   as a pass.
5. The case schema `case/v1` gains the optional `typed` member. This is an
   additive amendment made before the first corpus release, so the schema
   version is unchanged.

## Consequences

- The generated numeric and boolean recipes carry typed expectations from their
  revision 2 onward. Revision 1 stays reproducible from history.
- Typed expectations always belong to a profile, so a different host binding
  can define a different conversion table without disputing the generic
  results.
