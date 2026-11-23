#!/usr/bin/env python3
"""Run the unit tests under TEST_DIR; fail unless at least one test body ran.

Equivalent to ``python3 -m unittest discover -s TEST_DIR`` from the current
directory, but the exit status also requires at least one executed test and
no discovery errors: on Python 3.9 to 3.11, unittest exits 0 when discovery
finds no tests. A test counts as executed when its test method was entered and
the test did not end as a whole-test skip; fixtures (setUp, cleanups, subtests
outside the method) cannot mark a test executed. Class, module and subtest
skips are neither counted nor treated as missing execution. Standard library
only (3.9+).

Usage: run-unit-tests.py TEST_DIR
"""

import functools
import os
import sys
import unittest

_SUBTEST = getattr(unittest.case, "_SubTest", ())


class CountingResult(unittest.TextTestResult):
    """Text result that records whole-test skips (not subtest skips)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.whole_skips = set()

    def addSkip(self, test, reason):
        if isinstance(test, unittest.TestCase) and not isinstance(test, _SUBTEST):
            self.whole_skips.add(test.id())
        super().addSkip(test, reason)


def _recording(method, test_id, entered):
    @functools.wraps(method)
    def body(*args, **kwargs):
        entered.add(test_id)
        return method(*args, **kwargs)

    return body


def instrument(suite, entered):
    """Wrap every test method so entering its body records the test id.

    Fixture callbacks (setUp, cleanups, subtests outside the body) cannot mark
    a test as executed; only the test method itself can.
    """
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            instrument(test, entered)
        elif isinstance(test, unittest.TestCase):
            name = test._testMethodName
            method = getattr(test, name, None)
            if method is None:
                continue

            setattr(test, name, _recording(method, test.id(), entered))


def main(argv: list) -> int:
    if len(argv) != 2:
        print("usage: run-unit-tests.py TEST_DIR", file=sys.stderr)
        return 2
    # Match `python3 -m unittest`, which puts the current directory, not this
    # script's directory, first on the import path.
    sys.path[0] = os.getcwd()
    loader = unittest.TestLoader()
    suite = loader.discover(argv[1])
    entered = set()
    instrument(suite, entered)
    result = unittest.TextTestRunner(verbosity=1, resultclass=CountingResult).run(suite)
    executed = entered - result.whole_skips
    if loader.errors:
        print(f"error: {len(loader.errors)} test module(s) failed to load", file=sys.stderr)
        return 1
    if not executed:
        print("error: no test was executed (none discovered, or all skipped)", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
