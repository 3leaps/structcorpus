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


def _verify_enforced(runtime, name, lim):
    """Read the created container's host config and require every limit to be present.

    A limit that the runtime silently dropped would otherwise only show up on hosts where
    it matters (for example swap), so this check runs on every host.
    """
    fields = ("Memory", "MemorySwap", "PidsLimit", "NetworkMode", "ReadonlyRootfs")
    fmt = " ".join("{{.HostConfig.%s}}" % f for f in fields)
    got = subprocess.run([runtime, "inspect", "-f", fmt, name], capture_output=True, text=True, timeout=30)
    want = "%d %d %d none true" % (lim["memory_bytes"], lim["memory_bytes"], lim["pids"])
    if got.returncode != 0 or got.stdout.strip() != want:
        raise Blocked("container limits not enforced as requested: got %r, want %r" % (got.stdout.strip(), want))


def _read_capped(stream, cap, sink, overflow):
    """Read up to cap bytes, then keep draining, count the excess, and signal overflow."""
    kept = bytearray()
    excess = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        room = cap - len(kept)
        if room > 0:
            kept += chunk[:room]
        over = max(0, len(chunk) - max(room, 0))
        if over:
            excess += over
            overflow.set()
    sink["data"] = bytes(kept)
    sink["excess"] = excess


def run_contained(image, argv, stdin_bytes, limits=None, runtime=None):
    """Run argv in image with enforced limits. Returns a result dict; never raises for case failures."""
    lim = dict(DEFAULTS, **(limits or {}))
    runtime = runtime or _runtime()
    mechanism = check_containment(runtime)
    name = "structcorpus-run-%d-%d" % (os.getpid(), int(time.monotonic() * 1e6))
    create = [
        runtime,
        "create",
        "-i",
        "--name",
        name,
        "--log-driver",
        "none",
        "--memory",
        str(lim["memory_bytes"]),
        "--memory-swap",
        str(lim["memory_bytes"]),
        "--pids-limit",
        str(lim["pids"]),
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=%d" % lim["tmpfs_bytes"],
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        image,
    ] + list(argv)
    made = subprocess.run(create, capture_output=True, text=True, timeout=120)
    if made.returncode != 0:
        raise Blocked(_explain_failure("could not create container", made.stderr))
    result = {"mechanism": mechanism, "limits": lim, "peak_memory": "not_measured"}
    try:
        _verify_enforced(runtime, name, lim)
        proc = subprocess.Popen(
            [runtime, "start", "-a", "-i", name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = {}, {}
        overflow = threading.Event()
        readers = [
            threading.Thread(target=_read_capped, args=(proc.stdout, lim["output_bytes"], out, overflow)),
            threading.Thread(target=_read_capped, args=(proc.stderr, lim["output_bytes"], err, overflow)),
        ]
        for t in readers:
            t.start()
        try:
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        # Wait for exit, the wall-clock limit, or output past the cap, whichever comes first.
        timed_out = False
        started = time.monotonic()
        deadline = started + lim["wall_ms"] / 1000.0
        while proc.poll() is None:
            if overflow.is_set():
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)
        if proc.poll() is None:
            subprocess.run([runtime, "kill", name], capture_output=True, timeout=30)
            proc.wait(timeout=30)
        elapsed = time.monotonic() - started
        for t in readers:
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
            output_excess=out.get("excess", 0) + err.get("excess", 0),
            timed_out=timed_out,
            elapsed_s=round(elapsed, 3),
        )
    finally:
        subprocess.run([runtime, "rm", "-f", name], capture_output=True, timeout=60)
    result["outcome"] = classify(result)
    return result


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
    ("network-denied", "wget -q -T 2 -O /dev/null http://example.com", b"", {"wall_ms": 8000}, "crash"),
    ("root-read-only", "echo x > /structcorpus-probe", b"", {}, "crash"),
    ("tmpfs-capped", "head -c 4000000 /dev/zero > /tmp/fill", b"", {"tmpfs_bytes": 1024 * 1024}, "crash"),
]

# Positive controls: the same operations succeed when the relevant limit is lifted, so a
# "crash" above is caused by that limit and not by an unrelated failure (missing tool, typo).
CONTROLS = [
    ("fork-bomb", "for i in $(seq 1 200); do sleep 0.2 & done; wait", {"pids": 1024, "wall_ms": 8000}),
    ("network-denied", "command -v wget", {}),
    ("root-read-only", "echo x > /tmp/structcorpus-probe", {}),
    ("tmpfs-capped", "head -c 400000 /dev/zero > /tmp/fill", {"tmpfs_bytes": 1024 * 1024}),
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
        if name == "output-flood":
            # Stopped on overflow, so well before its wall limit; capture stays bounded.
            good = good and len(r["stdout"]) <= lim["output_bytes"] and r["elapsed_s"] < 0.5 * lim["wall_ms"] / 1000.0
        ok = ok and good
        results.append({"name": name, "want": want, "got": r["outcome"], "ok": good, "exit_code": r["exit_code"]})
    for name, cmd, lim in CONTROLS:
        r = run_contained(image, ["sh", "-c", cmd], b"", lim, runtime)
        good = r["outcome"] == "pass"
        ok = ok and good
        results.append(
            {"name": name + " (control)", "want": "pass", "got": r["outcome"], "ok": good, "exit_code": r["exit_code"]}
        )
    return results, ok


def cmd_selftest(args):
    try:
        results, ok = run_selftests(runtime=args.runtime)
    except Blocked as exc:
        print("selftest: blocked: %s" % exc)
        # Blocked is an honest, distinct outcome; --require-containment makes it a failure.
        return 1 if args.require_containment else 0
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
    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help(sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
