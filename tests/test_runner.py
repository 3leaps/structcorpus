"""Runtime-free tests for tools/runner.py (Python 3.9+ stdlib).

The real containment self-test (`make stress-selftest`) needs a container runtime and runs on
developer machines. These tests cover classification, capped output, and the blocked paths with
a fake runtime, so they run anywhere.
"""

import io
import json
import os
import stat
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import runner  # noqa: E402


def raw(**kw):
    base = {"oom_killed": False, "timed_out": False, "output_excess": 0, "exit_code": 0}
    base.update(kw)
    return base


class TestClassify(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(runner.classify(raw()), "pass")

    def test_crash(self):
        self.assertEqual(runner.classify(raw(exit_code=1)), "crash")

    def test_memory_limit_wins_over_timeout_and_exit(self):
        # An OOM kill also exits 137; it must never be reported as a crash or a timeout.
        self.assertEqual(runner.classify(raw(oom_killed=True, timed_out=True, exit_code=137)), "memory-limit")

    def test_output_limit_wins_over_timeout(self):
        # A flood is stopped for output, not reported as running out of time.
        self.assertEqual(runner.classify(raw(output_excess=10, timed_out=True, exit_code=137)), "output-limit")

    def test_timeout(self):
        self.assertEqual(runner.classify(raw(timed_out=True, exit_code=137)), "timeout")

    def test_outcomes_are_declared(self):
        for r in (raw(), raw(exit_code=1), raw(oom_killed=True), raw(output_excess=1), raw(timed_out=True)):
            self.assertIn(runner.classify(r), runner.OUTCOMES)


class TestOutputBudget(unittest.TestCase):
    def read(self, data, budget):
        sink = {}
        runner._read_capped(io.BytesIO(data), budget, sink)
        return sink["data"]

    def test_keeps_cap_counts_excess_and_signals(self):
        b = runner.OutputBudget(10)
        self.assertEqual(self.read(b"a" * 100, b), b"a" * 10)
        self.assertEqual((b.excess, b.overflow.is_set()), (90, True))

    def test_under_cap(self):
        b = runner.OutputBudget(10)
        self.assertEqual(self.read(b"abc", b), b"abc")
        self.assertEqual((b.excess, b.overflow.is_set()), (0, False))

    def test_exactly_at_cap_is_not_overflow(self):
        b = runner.OutputBudget(10)
        self.read(b"x" * 10, b)
        self.assertEqual((b.excess, b.overflow.is_set()), (0, False))

    def test_budget_is_shared_across_streams(self):
        # stdout and stderr draw from one budget: the documented cap is the total.
        b = runner.OutputBudget(10)
        out = self.read(b"o" * 6, b)
        err = self.read(b"e" * 6, b)
        self.assertEqual(len(out) + len(err), 10)
        self.assertEqual((b.excess, b.overflow.is_set()), (2, True))


class FakeRuntime(unittest.TestCase):
    """A stub executable standing in for the container runtime."""

    def make(self, script):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "fake-runtime")
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n" + script)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def tearDown(self):
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()


@unittest.skipIf(os.name == "nt", "shell stub")
class TestBlocked(FakeRuntime):
    def test_missing_runtime(self):
        with self.assertRaises(runner.Blocked) as ctx:
            runner.check_containment("structcorpus-no-such-runtime")
        self.assertIn("not found", str(ctx.exception))

    def test_runtime_not_answering(self):
        with self.assertRaises(runner.Blocked) as ctx:
            runner.check_containment(self.make("echo 'Cannot connect to the daemon' >&2; exit 1\n"))
        self.assertIn("unavailable", str(ctx.exception))

    def test_cgroup_v1_is_blocked(self):
        with self.assertRaises(runner.Blocked) as ctx:
            runner.check_containment(self.make("echo 1\n"))
        self.assertIn("cgroup v2 is required", str(ctx.exception))

    def test_cgroup_v2_is_accepted(self):
        self.assertIn("cgroup v2", runner.check_containment(self.make("echo 2\n")))

    def test_hazardous_run_never_starts_without_containment(self):
        # Blocked must be raised before any container is created.
        rt = self.make('case "$1" in info) echo 1;; *) echo RAN >> "$0.log";; esac\n')
        with self.assertRaises(runner.Blocked):
            runner.run_contained("image", ["true"], b"", runtime=rt)
        self.assertFalse(os.path.exists(rt + ".log"))

    def test_dropped_limit_is_blocked_before_start(self):
        # The runtime accepts the create but reports no swap cap: the case must not start.
        lim = runner.DEFAULTS
        report = "%d 0 %d none true" % (lim["memory_bytes"], lim["pids"])
        rt = self.make(
            'case "$1" in\n'
            "  info) echo 2;;\n"
            "  create) exit 0;;\n"
            "  inspect) echo '%s';;\n"
            '  start) echo STARTED >> "$0.log";;\n'
            "  *) exit 0;;\n"
            "esac\n" % report
        )
        with self.assertRaises(runner.Blocked) as ctx:
            runner.run_contained("image", ["true"], b"", runtime=rt)
        self.assertIn("not enforced", str(ctx.exception))
        self.assertFalse(os.path.exists(rt + ".log"))

    def test_storage_exhaustion_is_named(self):
        rt = self.make("echo 'write /var/lib/docker/tmp: no space left on device' >&2; exit 1\n")
        with self.assertRaises(runner.Blocked) as ctx:
            runner.check_containment(rt)
        self.assertIn("out of storage", str(ctx.exception))

    def test_cleanup_filters_by_runner_label(self):
        # cleanup must ask the runtime only for labelled containers and remove exactly those.
        rt = self.make('echo "$*" >> "$0.log"\ncase "$1" in info) echo 2;; ps) echo abc123;; *) ;; esac\n')
        self.assertEqual(runner.cleanup(rt), ["abc123"])
        with open(rt + ".log") as fh:
            calls = fh.read().splitlines()
        self.assertIn("ps -aq --filter label=" + runner.LABEL, calls)
        self.assertIn("rm -f abc123", calls)

    def test_selftest_reports_blocked(self):
        rt = self.make("exit 1\n")
        self.assertEqual(runner.main(["selftest", "--runtime", rt]), 0)
        self.assertEqual(runner.main(["selftest", "--runtime", rt, "--require-containment"]), 1)


class TestDefaults(unittest.TestCase):
    def test_secdr_0002_defaults(self):
        self.assertEqual(runner.DEFAULTS["wall_ms"], 2000)
        self.assertEqual(runner.DEFAULTS["memory_bytes"], 512 * 1024 * 1024)
        self.assertEqual(runner.DEFAULTS["output_bytes"], 64 * 1024)
        self.assertEqual(runner.DEFAULTS["pids"], 64)

    def test_selftest_image_is_digest_pinned(self):
        self.assertRegex(runner.SELFTEST_IMAGE, r"@sha256:[0-9a-f]{64}$")

    def test_every_crash_control_has_a_positive_control(self):
        crash = {name for name, _, _, _, want in runner.SELFTESTS if want == "crash"}
        self.assertEqual(crash, {name for name, _, _ in runner.CONTROLS})


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(os.name == "nt", "shell stub")
class TestRunCases(FakeRuntime):
    """`runner.py run` over a real hydrated root, with no container runtime."""

    @classmethod
    def setUpClass(cls):
        import corpus

        cls._out = tempfile.TemporaryDirectory()
        cls.root = os.path.join(cls._out.name, "h")
        corpus.hydrate(corpus.ROOT, cls.root, "stress", {"ladder-depth", "resource-boundaries"})

    @classmethod
    def tearDownClass(cls):
        cls._out.cleanup()

    def test_blocked_runtime_reports_every_hazardous_case(self):
        rt = self.make('case "$1" in info) echo 1;; *) echo RAN >> "$0.log";; esac\n')
        rows = list(runner.run_cases(self.root, "image", ["true"], runtime=rt))
        self.assertEqual(len(rows), 8)  # the depth ladder; the boundaries carry no hazards
        self.assertEqual({r["outcome"] for r in rows}, {"blocked"})
        self.assertFalse(os.path.exists(rt + ".log"))

    def test_all_includes_non_hazardous_cases(self):
        rt = self.make('case "$1" in info) echo 1;; esac\n')
        rows = list(runner.run_cases(self.root, "image", ["true"], hazardous_only=False, runtime=rt))
        self.assertEqual(len(rows), 8 + 12)

    def test_tampered_root_is_refused_before_running(self):
        import shutil

        bad = os.path.join(self._out.name, "tampered")
        shutil.copytree(self.root, bad)
        target = os.path.join(bad, "inputs", "yaml", "ladder-depth", "depth-0008.yaml")
        with open(target, "ab") as fh:
            fh.write(b"#")
        rt = self.make('case "$1" in info) echo 2;; *) echo RAN >> "$0.log";; esac\n')
        with self.assertRaises(ValueError):
            list(runner.run_cases(bad, "image", ["true"], runtime=rt))
        self.assertFalse(os.path.exists(rt + ".log"))

    def test_results_carry_no_raw_output(self):
        fake = {
            "limits": dict(runner.DEFAULTS, wall_ms=2000),
            "mechanism": "cgroup v2 (docker)",
            "peak_memory": "not_measured",
            "outcome": "pass",
            "exit_code": 0,
            "oom_killed": False,
            "elapsed_s": 0.1,
            "stdout": b"\x1b[31mhostile",
            "output_excess": 0,
        }
        rt = self.make('case "$1" in info) echo 2;; esac\n')
        original = runner.run_contained
        runner.run_contained = lambda *a, **k: fake
        try:
            rows = list(runner.run_cases(self.root, "image", ["true"], runtime=rt))
        finally:
            runner.run_contained = original
        self.assertTrue(rows)
        for r in rows:
            self.assertNotIn("stdout", r)
            self.assertEqual(r["stdout_bytes"], len(fake["stdout"]))
            self.assertNotIn("hostile", json.dumps(r))

    def test_results_record_enforcement_not_measurement(self):
        fake = {
            "outcome": "pass",
            "exit_code": 0,
            "oom_killed": False,
            "elapsed_s": 0.1,
            "stdout": b"",
            "output_excess": 0,
            "limits": dict(runner.DEFAULTS),
            "mechanism": "cgroup v2 (docker)",
            "peak_memory": "not_measured",
        }
        rt = self.make('case "$1" in info) echo 2;; esac\n')
        original = runner.run_contained
        runner.run_contained = lambda *a, **k: fake
        try:
            [row, *_] = list(runner.run_cases(self.root, "image", ["true"], runtime=rt))
        finally:
            runner.run_contained = original
        self.assertEqual(row["peak_memory"], "not_measured")
        self.assertEqual(row["mechanism"], "cgroup v2 (docker)")
        self.assertEqual(set(row["limits"]), set(runner.DEFAULTS))
