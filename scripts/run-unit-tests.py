#!/usr/bin/env python3
"""Run the unit tests under TEST_DIR; fail on a vacuous or failing run.

Equivalent to ``python3 -m unittest discover -s TEST_DIR`` from the current
directory, but it also fails when the run is vacuous: no test invocation
reached an outcome other than a whole-test skip. On Python 3.9 to 3.11,
unittest itself exits 0 when discovery finds no tests.

Contract. Each test invocation the runner starts counts once (two invocations
of the same test id count twice) unless that invocation ends as a whole-test
skip. Skips of subtests, classes or modules, and fixture callbacks, neither
count nor cancel an invocation. An invocation whose callable, as resolved when
it starts, would return an unrun body fails the run: generator and
async-generator functions, and coroutine functions outside an
IsolatedAsyncioTestCase, reached through bound methods, functools.partial or
partialmethod, callable objects, or FunctionTestCase. Other dynamic forms are
outside that check. Tests are not modified.

The gate detects accidental vacuity in the runner's reported lifecycle
(nothing discovered, everything skipped). It does not prove that arbitrary
test code exercised anything; whether a test asserts anything is a review
question. Standard library only (Python 3.9+).

Usage: run-unit-tests.py TEST_DIR
"""

import functools
import inspect
import os
import sys
import unittest


def _effective_function(target):
    """Unwrap the adapters unittest commonly invokes through."""
    for _ in range(16):
        if isinstance(target, (staticmethod, classmethod)):
            target = target.__func__
        elif isinstance(target, functools.partial):
            target = target.func
        elif inspect.ismethod(target):
            target = target.__func__
        elif inspect.isfunction(target) or inspect.isbuiltin(target):
            return target
        elif callable(target):
            call = inspect.getattr_static(type(target), "__call__", None)
            if call is None or call is target:
                return target
            target = call
        else:
            return target
    return target


def defers_body(test):
    """True when the callable this invocation will run returns an unrun body.

    Inspects the callable as resolved at the start of the invocation (after
    any instance, load_tests or run() rebinding), unwrapping bound methods,
    functools.partial and partialmethod, callable objects' __call__, and
    FunctionTestCase. Generator and async-generator functions, and coroutine
    functions outside IsolatedAsyncioTestCase, are deferred. Other dynamic
    forms are outside this check. Never alters what runs.
    """
    if isinstance(test, unittest.FunctionTestCase):
        target = getattr(test, "_testFunc", None)
    else:
        try:
            target = getattr(test, test._testMethodName)
        except Exception:
            return False
    function = _effective_function(target)
    if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        return True
    if inspect.iscoroutinefunction(function):
        return not isinstance(test, unittest.IsolatedAsyncioTestCase)
    return False


class CountingResult(unittest.TextTestResult):
    """Text result that counts started invocations not ending as whole skips."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed = 0
        self.deferred = []
        self._current = None
        self._current_skipped = False

    def startTest(self, test):
        self._current = test
        self._current_skipped = False
        if defers_body(test):
            self.deferred.append(test.id())
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
    result = unittest.TextTestRunner(verbosity=1, resultclass=CountingResult).run(suite)
    if result.deferred:
        names = ", ".join(sorted(set(result.deferred)))
        print(f"error: test bodies unittest would not run: {names}", file=sys.stderr)
        return 1
    if result.executed == 0:
        print("error: no test was executed (none discovered, or all skipped)", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
