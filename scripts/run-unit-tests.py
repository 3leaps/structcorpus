#!/usr/bin/env python3
"""Run the unit tests under TEST_DIR; fail on a vacuous or failing run.

Equivalent to ``python3 -m unittest discover -s TEST_DIR`` from the current
directory, but it also fails when the run is vacuous: no test invocation
reached an outcome other than a whole-test skip. On Python 3.9 to 3.11,
unittest itself exits 0 when discovery finds no tests.

Contract. Each test invocation the runner starts counts once (two invocations
of the same test id count twice) unless that invocation ends as a whole-test
skip. Skips of subtests, classes or modules, and fixture callbacks, neither
count nor cancel an invocation. Test methods whose bodies plain unittest would
never run are refused before running: generator and async-generator methods,
and coroutine methods outside an IsolatedAsyncioTestCase. Tests are not
modified. The gate guards against accidental vacuity (nothing discovered,
everything skipped); whether a test asserts anything is a review question.
Standard library only (Python 3.9+).

Usage: run-unit-tests.py TEST_DIR
"""

import inspect
import os
import sys
import unittest


class CountingResult(unittest.TextTestResult):
    """Text result that counts started invocations not ending as whole skips."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed = 0
        self._current = None
        self._current_skipped = False

    def startTest(self, test):
        self._current = test
        self._current_skipped = False
        super().startTest(test)

    def addSkip(self, test, reason):
        # Only a skip of the started invocation itself cancels it; subtest,
        # class and module skips arrive with other objects.
        if test is self._current:
            self._current_skipped = True
        super().addSkip(test, reason)

    def stopTest(self, test):
        if test is self._current and not self._current_skipped:
            self.executed += 1
        self._current = None
        super().stopTest(test)


def deferred_bodies(suite):
    """Yield ids of tests whose method plain unittest would not actually run."""
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from deferred_bodies(test)
            continue
        if not isinstance(test, unittest.TestCase):
            continue
        method = inspect.getattr_static(type(test), getattr(test, "_testMethodName", ""), None)
        method = getattr(method, "__func__", method)
        if inspect.isgeneratorfunction(method) or inspect.isasyncgenfunction(method):
            yield test.id()
        elif inspect.iscoroutinefunction(method) and not isinstance(test, unittest.IsolatedAsyncioTestCase):
            yield test.id()


def main(argv: list) -> int:
    if len(argv) != 2:
        print("usage: run-unit-tests.py TEST_DIR", file=sys.stderr)
        return 2
    # Match `python3 -m unittest`, which puts the current directory, not this
    # script's directory, first on the import path.
    sys.path[0] = os.getcwd()
    loader = unittest.TestLoader()
    suite = loader.discover(argv[1])
    if loader.errors:
        print(f"error: {len(loader.errors)} test module(s) failed to load", file=sys.stderr)
        return 1
    deferred = sorted(set(deferred_bodies(suite)))
    if deferred:
        print("error: test methods unittest would not run: " + ", ".join(deferred), file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=1, resultclass=CountingResult).run(suite)
    if result.executed == 0:
        print("error: no test was executed (none discovered, or all skipped)", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
