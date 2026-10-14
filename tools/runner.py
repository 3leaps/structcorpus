#!/usr/bin/env python3
"""Bounded execution of hostile inputs (SecDR-0002), Python 3.9+ standard library only.

Each input runs in its own container, created with an enforced cgroup v2
memory limit (no swap), a process limit, no network, a read-only root, and
a small tmpfs. The input arrives on stdin, and the runner caps captured
output and wall time itself. The parser being exercised is the caller's
image and command. This module ships no parser (ADR-0001).

Outcomes are kept distinct: pass, mismatch, crash, timeout, memory-limit,
output-limit, blocked, skipped, unrun. When the required mechanism (a
container runtime on a cgroup v2 host) is unavailable, the outcome is
blocked, never an unbounded run.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

# Every runner container carries this label, so leftovers from an interrupted runner can be
# found and removed without touching anything else on the host.
LABEL = "org.3leaps.structcorpus.runner=1"

DEFAULTS = {
    "wall_ms": 2000,
    "memory_bytes": 512 * 1024 * 1024,
    "output_bytes": 64 * 1024,
    "pids": 64,
    "tmpfs_bytes": 1024 * 1024,
}
OUTCOMES = ("pass", "mismatch", "crash", "timeout", "memory-limit", "output-limit", "blocked", "skipped", "unrun")
# Multi-architecture index digest of the image used only by the runner self-tests.
SELFTEST_IMAGE = "alpine:3@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6"


class Blocked(Exception):
    """The required containment mechanism is not available."""


def _runtime():
    return os.environ.get("STRUCTCORPUS_CONTAINER_RUNTIME", "docker")


def check_containment(runtime=None):
    """Return a description of the enforcing mechanism, or raise Blocked."""
    runtime = runtime or _runtime()
    if shutil.which(runtime) is None:
        raise Blocked("container runtime %r not found" % runtime)
    try:
        proc = subprocess.run(
            [runtime, "info", "--format", "{{.CgroupVersion}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("container runtime unavailable (is it started?): %s" % exc) from None
    if proc.returncode != 0:
        raise Blocked(_explain_failure("container runtime unavailable (is it started?)", proc.stderr))
    if proc.stdout.strip() != "2":
        raise Blocked("cgroup v2 is required; runtime reports cgroup version %r" % proc.stdout.strip())
    return "%s with cgroup v2 memory.max per container" % runtime


STORAGE_MARKERS = ("no space left on device", "disk quota exceeded", "not enough space")


def _explain_failure(what, stderr):
    """Name storage exhaustion explicitly; it is an operator problem, not a case result."""
    text = (stderr or "").strip()
    if any(m in text.lower() for m in STORAGE_MARKERS):
        return (
            "%s: the container runtime is out of storage. Free space in the runtime's disk "
            "(for example by pruning unused images) and retry. Detail: %s" % (what, text[:200])
        )
    return "%s: %s" % (what, text[:300])


def _verify_enforced(runtime, name, lim, lift=None):
    """Read the created container's host config and require every limit to be present.

    A limit that the runtime silently dropped would otherwise only show up on hosts where
    it matters (for example swap), so this check runs on every host.
    """
    fmt = (
        "{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.PidsLimit}} "
        "{{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}} {{.HostConfig.LogConfig.Type}} "
        "{{json .HostConfig.CapDrop}} {{json .HostConfig.SecurityOpt}} {{json .HostConfig.Tmpfs}} "
        '{{index .Config.Labels "org.3leaps.structcorpus.runner"}}'
    )
    got = subprocess.run([runtime, "inspect", "-f", fmt, name], capture_output=True, text=True, timeout=30)
    compact = {"separators": (",", ":")}  # matches the runtime's {{json}} output
    tmpfs = json.dumps({"/tmp": "rw,noexec,nosuid,size=%d" % lim["tmpfs_bytes"]}, **compact)
    want = "%d %d %d %s %s none %s %s %s 1" % (
        lim["memory_bytes"],
        lim["memory_bytes"],
        lim["pids"],
        "bridge" if lift == "network" else "none",
        "false" if lift == "read_only" else "true",
        json.dumps(["ALL"], **compact),
        json.dumps(["no-new-privileges"], **compact),
        tmpfs,
    )
    if got.returncode != 0 or got.stdout.strip() != want:
        raise Blocked("container limits not enforced as requested: got %r, want %r" % (got.stdout.strip(), want))


class OutputBudget:
    """One captured-output budget shared by stdout and stderr (SecDR-0002 output cap)."""

    def __init__(self, cap):
        self.cap = cap
        self.used = 0
        self.excess = 0
        self.overflow = threading.Event()
        self._lock = threading.Lock()

    def take(self, n):
        """Reserve up to n bytes; returns how many may be kept and records any excess."""
        with self._lock:
            room = max(0, self.cap - self.used)
            keep = min(n, room)
            self.used += keep
            if n > keep:
                self.excess += n - keep
                self.overflow.set()
            return keep


def _read_capped(stream, budget, sink):
    """Keep what the shared budget allows, then keep draining so the child never blocks on a full pipe."""
    kept = bytearray()
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        keep = budget.take(len(chunk))
        kept += chunk[:keep]
    sink["data"] = bytes(kept)


def run_contained(image, argv, stdin_bytes, limits=None, runtime=None):
    """Run argv in image with every limit enforced. Returns a result dict; never raises for case failures."""
    return _run(image, argv, stdin_bytes, limits, runtime, lift=None)


# Limits a positive control may lift, one at a time. Only the self-test reaches this path.
_LIFTABLE = ("network", "read_only")


def _run(image, argv, stdin_bytes, limits, runtime, lift):
    if lift is not None and lift not in _LIFTABLE:
        raise ValueError("cannot lift %r" % lift)
    lim = dict(DEFAULTS, **(limits or {}))
    runtime = runtime or _runtime()
    mechanism = check_containment(runtime)
    name = "structcorpus-run-%d-%d" % (os.getpid(), int(time.monotonic() * 1e6))
    create = (
        [
            runtime,
            "create",
            "-i",
            "--name",
            name,
            "--label",
            LABEL,
            "--log-driver",
            "none",
            "--memory",
            str(lim["memory_bytes"]),
            "--memory-swap",
            str(lim["memory_bytes"]),
            "--pids-limit",
            str(lim["pids"]),
            "--network",
            "bridge" if lift == "network" else "none",
        ]
        + ([] if lift == "read_only" else ["--read-only"])
        + [
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=%d" % lim["tmpfs_bytes"],
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            image,
        ]
        + list(argv)
    )
    made = subprocess.run(create, capture_output=True, text=True, timeout=120)
    if made.returncode != 0:
        raise Blocked(_explain_failure("could not create container", made.stderr))
    result = {"mechanism": mechanism, "limits": lim, "peak_memory": "not_measured"}
    try:
        _verify_enforced(runtime, name, lim, lift)
        proc = subprocess.Popen(
            [runtime, "start", "-a", "-i", name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # The deadline starts before any input is written: a case that never reads its
        # input cannot stall the runner, because the write happens on its own thread.
        started = time.monotonic()
        deadline = started + lim["wall_ms"] / 1000.0
        out, err = {}, {}
        budget = OutputBudget(lim["output_bytes"])
        threads = [
            threading.Thread(target=_read_capped, args=(proc.stdout, budget, out), daemon=True),
            threading.Thread(target=_read_capped, args=(proc.stderr, budget, err), daemon=True),
            threading.Thread(target=_write_input, args=(proc.stdin, stdin_bytes), daemon=True),
        ]
        for t in threads:
            t.start()
        # Wait for exit, the wall-clock limit, or output past the cap, whichever comes first.
        timed_out = False
        while proc.poll() is None:
            if budget.overflow.is_set():
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)
        stopped_by_runner = proc.poll() is None
        if stopped_by_runner:
            subprocess.run([runtime, "kill", name], capture_output=True, timeout=30)
            proc.wait(timeout=30)
        elapsed = time.monotonic() - started
        for t in threads:
            t.join(timeout=30)
        state = json.loads(
            subprocess.run(
                [runtime, "inspect", "-f", "{{json .State}}", name], capture_output=True, text=True, timeout=30
            ).stdout
            or "{}"
        )
        result.update(
            exit_code=state.get("ExitCode"),
            oom_killed=bool(state.get("OOMKilled")),
            stdout=out.get("data", b""),
            stderr=err.get("data", b""),
            output_excess=budget.excess,
            # Asked of the runtime before removal: a stop must end the whole container,
            # not only the attached client process.
            container_stopped=_still_running(runtime, name) is False,
            timed_out=timed_out,
            elapsed_s=round(elapsed, 3),
        )
    finally:
        subprocess.run([runtime, "rm", "-f", name], capture_output=True, timeout=60)
    result["outcome"] = classify(result)
    return result


def _still_running(runtime, name):
    """True or False from the runtime; None if it cannot say."""
    got = subprocess.run(
        [runtime, "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True, timeout=30
    )
    if got.returncode != 0:
        return None
    return got.stdout.strip() == "true"


def _write_input(pipe, data):
    try:
        pipe.write(data)
    except (BrokenPipeError, OSError):
        pass  # the case exited or was killed without reading all of its input
    finally:
        try:
            pipe.close()
        except (BrokenPipeError, OSError):
            pass


def classify(r):
    """Map a raw run to a SecDR-0002 outcome. Comparing output to an expectation is the caller's job."""
    if r["oom_killed"]:
        return "memory-limit"
    if r["output_excess"] > 0:
        return "output-limit"
    if r["timed_out"]:
        return "timeout"
    if r["exit_code"] != 0:
        return "crash"
    return "pass"


# ---- self-tests: prove each control is enforced before any hostile case runs ----

NETWORK_PROBE = 'gw=$(ip route | awk \'/default/ {print $3}\'); [ -n "$gw" ] && ping -c1 -W2 "$gw"'

SELFTESTS = [
    # (name, shell command, stdin, limit overrides, expected outcome)
    ("echo-stdin", "cat", b"structcorpus\n", {}, "pass"),
    (
        "memory-hog",
        "head -c 400000000 /dev/zero | tr '\\0' a | sort > /dev/null",
        b"",
        {"memory_bytes": 32 * 1024 * 1024},
        "memory-limit",
    ),
    ("wall-clock", "sleep 30", b"", {"wall_ms": 1500}, "timeout"),
    ("output-flood", "yes structcorpus", b"", {"output_bytes": 4096, "wall_ms": 10000}, "output-limit"),
    ("fork-bomb", "for i in $(seq 1 200); do sleep 5 & done; wait", b"", {"pids": 16, "wall_ms": 8000}, "crash"),
    # Reaches the runtime's own bridge gateway, so the check needs no internet access.
    ("network-denied", NETWORK_PROBE, b"", {"wall_ms": 8000}, "crash"),
    ("root-read-only", "echo x > /structcorpus-probe", b"", {}, "crash"),
    ("tmpfs-capped", "head -c 4000000 /dev/zero > /tmp/fill", b"", {"tmpfs_bytes": 1024 * 1024}, "crash"),
    # A background child keeps producing output after its parent; the wall limit must stop
    # the whole container, not only the parent shell.
    ("descendant-timeout", "(while :; do echo tick; sleep 0.1; done) & sleep 30", b"", {"wall_ms": 1500}, "timeout"),
    # A case that never reads a large input must still be stopped at the wall limit.
    ("unread-input", "sleep 30", b"x" * (16 * 1024 * 1024), {"wall_ms": 1500}, "timeout"),
    # Both streams flood at once; the cap applies to their total.
    ("split-flood", "yes out & yes err >&2", b"", {"output_bytes": 4096, "wall_ms": 10000}, "output-limit"),
]

# Positive controls: the identical command succeeds when exactly that limit is lifted, so a
# "crash" above is caused by the limit and not by an unrelated failure (missing tool, typo).
# (name, limit overrides, limit lifted)
CONTROLS = [
    ("fork-bomb", {"pids": 1024, "wall_ms": 8000}, None),
    ("network-denied", {"wall_ms": 8000}, "network"),
    ("root-read-only", {}, "read_only"),
    ("tmpfs-capped", {"tmpfs_bytes": 8 * 1024 * 1024}, None),
]


def run_selftests(image=SELFTEST_IMAGE, runtime=None):
    """Run every control. Returns (results, all_ok). Raises Blocked if containment is unavailable."""
    check_containment(runtime)
    results = []
    ok = True
    for name, cmd, stdin, lim, want in SELFTESTS:
        r = run_contained(image, ["sh", "-c", cmd], stdin, lim, runtime)
        good = r["outcome"] == want
        if name == "echo-stdin":
            good = good and r["stdout"] == stdin
        if want in ("timeout", "output-limit", "memory-limit"):
            good = good and r["container_stopped"]
        if name in ("descendant-timeout", "unread-input"):
            # The case would otherwise run 30 s; a generous bound absorbs host scheduling
            # jitter while still failing a runner that does not stop it.
            good = good and r["elapsed_s"] < lim["wall_ms"] / 1000.0 + 8
        if name == "split-flood":
            good = good and len(r["stdout"]) + len(r["stderr"]) <= lim["output_bytes"]
        if name == "output-flood":
            # Stopped on overflow, so well before its wall limit; capture stays bounded.
            good = good and len(r["stdout"]) <= lim["output_bytes"] and r["elapsed_s"] < 0.5 * lim["wall_ms"] / 1000.0
        ok = ok and good
        results.append({"name": name, "want": want, "got": r["outcome"], "ok": good, "exit_code": r["exit_code"]})
    commands = {name: cmd for name, cmd, _, _, _ in SELFTESTS}
    for name, lim, lift in CONTROLS:
        cmd = commands[name]
        if name == "fork-bomb":
            cmd = cmd.replace("sleep 5", "sleep 0.2")  # same fan-out, finishing within the wall limit
        r = _run(image, ["sh", "-c", cmd], b"", lim, runtime, lift)
        good = r["outcome"] == "pass"
        ok = ok and good
        results.append(
            {"name": name + " (control)", "want": "pass", "got": r["outcome"], "ok": good, "exit_code": r["exit_code"]}
        )
    return results, ok


def leftovers(runtime=None):
    """IDs of runner containers that still exist (for example after an interrupted runner)."""
    runtime = runtime or _runtime()
    got = subprocess.run(
        [runtime, "ps", "-aq", "--filter", "label=" + LABEL], capture_output=True, text=True, timeout=30
    )
    return got.stdout.split() if got.returncode == 0 else []


def cleanup(runtime=None):
    """Remove leftover runner containers. Touches only containers carrying the runner label."""
    runtime = runtime or _runtime()
    ids = leftovers(runtime)
    if ids:
        subprocess.run([runtime, "rm", "-f"] + ids, capture_output=True, timeout=120)
    return ids


def cmd_cleanup(args):
    try:
        check_containment(args.runtime)
    except Blocked as exc:
        print("cleanup: blocked: %s" % exc)
        return 1
    removed = cleanup(args.runtime)
    print("cleanup: removed %d runner container(s)" % len(removed))
    return 0


def cmd_selftest(args):
    try:
        results, ok = run_selftests(runtime=args.runtime)
    except Blocked as exc:
        print("selftest: blocked: %s" % exc)
        # Blocked is an honest, distinct outcome; --require-containment makes it a failure.
        return 1 if args.require_containment else 0
    left = leftovers(args.runtime)
    if left:
        ok = False
        results.append({"name": "no-leftovers", "want": "0", "got": str(len(left)), "ok": False, "exit_code": None})
    else:
        results.append({"name": "no-leftovers", "want": "0", "got": "0", "ok": True, "exit_code": None})
    for r in results:
        print("%-26s want %-13s got %-13s %s" % (r["name"], r["want"], r["got"], "ok" if r["ok"] else "FAIL"))
    print("selftest: %s" % ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="runner.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command")
    st = sub.add_parser("selftest", help="prove the containment controls are enforced")
    st.add_argument(
        "--runtime", default=None, help="container runtime (default: $STRUCTCORPUS_CONTAINER_RUNTIME or docker)"
    )
    st.add_argument("--require-containment", action="store_true", help="fail instead of reporting blocked")
    st.set_defaults(func=cmd_selftest)
    cl = sub.add_parser("cleanup", help="remove leftover runner containers (only those the runner labelled)")
    cl.add_argument("--runtime", default=None)
    cl.set_defaults(func=cmd_cleanup)
    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help(sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
