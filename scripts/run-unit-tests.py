#!/usr/bin/env python3
"""Run the unit tests under TEST_DIR; fail on a vacuous or failing run.

Equivalent to ``python3 -m unittest discover -s TEST_DIR`` from the current
directory, but it also fails when the run is vacuous: no test invocation
reached an outcome other than a whole-test skip. On Python 3.9 to 3.11,
unittest itself exits 0 when discovery finds no tests.

Contract. Each test invocation the runner starts counts once (two invocations
of the same test id count twice) unless that invocation ends as a whole-test
skip. Skips of subtests, classes or modules, and fixture callbacks, neither
count nor cancel an invocation. An invocation whose test callable, looked up
statically when it starts, would return an unrun body fails the run (see
defers_body: generator and async-generator functions, and coroutines other
than an IsolatedAsyncioTestCase's own async test method, reached directly or
through bindings, functools.partial/partialmethod, callable objects or
FunctionTestCase). Properties and other descriptors are not invoked, so that
check has no side effects; forms behind them are outside it. Tests are not
modified.

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


def _unwrap_binding(target):
    """Unwrap method bindings only (bound method, staticmethod, classmethod)."""
    while True:
        if isinstance(target, (staticmethod, classmethod)) or inspect.ismethod(target):
            target = target.__func__
        else:
            return target


def _effective_function(target):
    """Unwrap bindings and the call adapters unittest may invoke through."""
    for _ in range(16):
        target = _unwrap_binding(target)
        if isinstance(target, (functools.partial, functools.partialmethod)):
            target = target.func
        elif inspect.isfunction(target) or inspect.isbuiltin(target) or isinstance(target, property):
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
    """True when this invocation's test callable returns a body it never runs.

    The callable is looked up statically when the invocation starts (instance
    attributes first, so __init__, load_tests or run() rebinding is seen),
    without invoking properties or other descriptors, so the lookup has no side
    effects and unittest's own lookup is unchanged. Bindings,
    functools.partial and partialmethod, callable objects' __call__ and
    FunctionTestCase are unwrapped. Generator and async-generator functions are
    deferred; a coroutine function is deferred unless it is the test method
    itself on an IsolatedAsyncioTestCase. Properties are not resolved.
    """
    if isinstance(test, unittest.FunctionTestCase):
        target = getattr(test, "_testFunc", None)
    else:
        target = inspect.getattr_static(test, test._testMethodName, None)
    function = _effective_function(target)
    if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        return True
    if inspect.iscoroutinefunction(function):
        direct = _unwrap_binding(target)
        awaited = isinstance(test, unittest.IsolatedAsyncioTestCase) and (inspect.iscoroutinefunction(direct))
        return not awaited
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
