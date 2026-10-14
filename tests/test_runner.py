"""Runtime-free tests for tools/runner.py (Python 3.9+ stdlib).

The real containment self-test (`make stress-selftest`) needs a container runtime and runs on
developer machines. These tests cover classification, capped output, and the blocked paths with
a fake runtime, so they run anywhere.
"""

import io
import os
import stat
import sys
import tempfile
import threading
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


class TestReadCapped(unittest.TestCase):
    def test_keeps_cap_counts_excess_and_signals(self):
        sink, overflow = {}, threading.Event()
        runner._read_capped(io.BytesIO(b"a" * 100), 10, sink, overflow)
        self.assertEqual(sink["data"], b"a" * 10)
        self.assertEqual(sink["excess"], 90)
        self.assertTrue(overflow.is_set())

    def test_under_cap(self):
        sink, overflow = {}, threading.Event()
        runner._read_capped(io.BytesIO(b"abc"), 10, sink, overflow)
        self.assertEqual((sink["data"], sink["excess"], overflow.is_set()), (b"abc", 0, False))

    def test_exactly_at_cap_is_not_overflow(self):
        sink, overflow = {}, threading.Event()
        runner._read_capped(io.BytesIO(b"x" * 10), 10, sink, overflow)
        self.assertEqual((sink["excess"], overflow.is_set()), (0, False))


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
