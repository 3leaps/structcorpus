# Running hostile cases

Corpus *use* needs only `python3`. Executing hazardous cases against a parser
needs a container runtime on a cgroup v2 host (Docker, or Colima on macOS)
([SecDR-0002](decisions/SecDR-0002-bounded-execution-containment.md)).

## Check the host

```sh
make stress-selftest
```

This fails fast if the runtime is not started, if it lacks cgroup v2, or if
it is out of storage. It then proves every control by running deliberately
hostile commands inside containers.

## Limits

| Limit | Default |
| --- | --- |
| Wall time | 2 s |
| Memory (no swap) | 512 MiB |
| Captured output | 64 KiB |
| Processes | 64 |
| Writable temporary space | 1 MiB |

## Outcomes

`pass`, `mismatch`, `crash`, `timeout`, `memory-limit`, `output-limit`,
`blocked`, `skipped`, `unrun`.

An OS kill is never a pass for a case that expects a specific limit error
from the parser. `blocked` means the required mechanism was unavailable; the
case did not run.

## Parsers

The corpus ships no parser. A consumer runs its own parser image and command
through `tools/runner.py`. Driver integration arrives with the hazardous
recipes.
