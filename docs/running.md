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

If a runner is interrupted, remove its leftovers with:

```sh
python3 tools/runner.py cleanup
```

This removes only containers the runner labelled.

## Limits

| Limit | Default |
| --- | --- |
| Wall time | 2 s |
| Memory (no swap) | 512 MiB |
| Captured output (stdout and stderr combined) | 64 KiB |
| Processes | 64 |
| Writable temporary space | 1 MiB |

## Outcomes

`pass`, `mismatch`, `crash`, `timeout`, `memory-limit`, `output-limit`,
`blocked`, `skipped`, `unrun`.

An OS kill is never a pass for a case that expects a specific limit error
from the parser. `blocked` means the required mechanism was unavailable; the
case did not run.

## Parsers

The corpus ships no parser. A consumer runs its own parser image, pinned by
digest, and command through `tools/runner.py`:

```sh
python3 tools/corpus.py hydrate --tier stress --output /path/outside/checkout
python3 tools/runner.py run --root /path/outside/checkout \
  --image registry.example.invalid/parser@sha256:... \
  --results results.jsonl -- parser-driver --profile yamlprims-core
```

`run` verifies the hydrated root first and runs nothing if verification fails.
By default it runs only hazardous cases (`--all` runs every case). Each case runs
in its own container with that case's budgets, and its input arrives on stdin.

Each line of `results.jsonl` gives:
- the case id and its outcome;
- the exit code;
- whether the memory limit was hit;
- the elapsed time;
- the length and sha256 of standard output.

Raw output is never stored. Comparing the parser's output with a case's
expectations is the driver's job; the runner only bounds the run.
