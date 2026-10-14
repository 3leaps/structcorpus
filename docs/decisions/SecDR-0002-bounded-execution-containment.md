---
Record: SecDR-0002
Title: Bounded execution and memory containment for hostile cases
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
Audience: public
---

# SecDR-0002: Bounded execution and memory containment for hostile cases

## Context

Some cases are designed to make a parser do excessive work: alias fan-out,
deep nesting, huge keys, late-failing documents. These cases are public
(SecDR-0001). Classification and execution hazard are independent, though,
so a public input can still exhaust a host.

An address-space limit (`RLIMIT_AS`) is the easy memory control, and it is
the wrong default. Sanitizer builds such as ASan reserve very large shadow
address ranges and fail at start-up under a modest address-space cap. Some
language runtimes reserve address space eagerly as well. A cap like that
fails before any input is parsed. This produces false failures in exactly
the fuzz and binding tiers, and an address-space limit is not a
resident-memory limit anyway.

## Decision

1. **Hydration never executes a candidate parser** (ADR-0001). Execution
   happens only through a separate, explicitly bounded runner.
2. **The memory control is a cgroup v2 `memory.max`** (or the platform's
   equivalent job or resource-group limit). An address-space limit may be
   used and recorded as a separate, weaker mechanism. It is never reported as
   a memory ceiling.
3. **Each tier declares which mechanisms it requires.** If a required
   mechanism is unavailable, the hazardous case is reported as **`blocked`**,
   not `skipped` and not passed. Only bounded safe sizes run.
4. **Defaults for one hostile child:** 2 s wall time, 512 MiB under the
   required memory mechanism, 64 KiB of captured output, and a capped
   temporary directory. The whole process group is killed and reaped.
   Network and filesystem access are constrained. Profiles may choose other
   finite bounds with a stated reason, and host ceilings take precedence.
   A plain `timeout` alone is not containment.
5. **Outcomes stay distinct:** `pass`, `mismatch`, `crash`, `timeout`,
   `memory-limit`, `output-limit`, `blocked`, `skipped`, and `unrun`. An OS
   kill does not satisfy a case that expects the adapter to return a
   specific limit error.
6. **Peak memory is measured for the child only.** Measurements from a
   parent interpreter do not count, and the measurement method is recorded
   with each result.
7. **Published results are sanitized:** no host paths, no environment
   dumps, and no secrets.

## Consequences

- Full stress and fuzz execution needs Linux with cgroup v2 delegation. On
  other platforms, hazardous cases appear as `blocked` with the reason, which
  reports coverage honestly.
- The runner needs its own tests covering timeouts of descendant processes,
  output flooding, and cases that exceed the memory limit. Hazardous
  execution stays disabled until those tests pass on the host.
- This record describes controls only, not the parser defects those controls
  defend against.

## Implementation note (runner)

`tools/runner.py` implements this record with one container per hostile case:
- a memory limit equal to the swap limit (no swap);
- a process limit;
- no network;
- a read-only root and a capped tmpfs;
- all capabilities dropped and `no-new-privileges` set;
- input on stdin.

The runner enforces wall time and the output cap itself, and stops a case as
soon as its output passes the cap. Before starting a case, it reads the
container's configuration back and refuses to run (`blocked`) if any limit
is missing. The runtime must report cgroup v2. A missing or stopped runtime,
or a runtime out of storage, is reported as `blocked`, with storage
exhaustion named explicitly.

Peak memory is recorded as `not_measured`. It is a measurement, not a gate,
and no supported post-exit source exists for it yet.

`make stress-selftest` proves each control on the host: memory, wall time,
output, processes, network, read-only root, and tmpfs. Every limit that
produces a crash is paired with a positive control showing the same operation
succeeds when the limit is lifted. The self-test is part of `make prepush`,
the pre-push and PR-final gate; CI does not run containers.
