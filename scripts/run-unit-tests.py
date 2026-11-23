#!/usr/bin/env python3
"""Run the unit tests under TEST_DIR; fail unless at least one test body ran.

Equivalent to ``python3 -m unittest discover -s TEST_DIR`` from the current
directory, but the exit status also requires at least one executed test and
no discovery errors: on Python 3.9 to 3.11, unittest exits 0 when discovery
finds no tests. A test counts as executed when its body reported an outcome
(success, failure, error, expected failure, unexpected success, or a subtest
result); a skipped test does not. Class, module and subtest skips are neither
counted nor treated as missing execution. Standard library only (3.9+).

Usage: run-unit-tests.py TEST_DIR
"""

import os
import sys
import unittest


class CountingResult(unittest.TextTestResult):
    """Text result that records the ids of tests whose bodies ran."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed = set()

    def _ran(self, test):
        if isinstance(test, unittest.TestCase):
            self.executed.add(test.id())

    def addSuccess(self, test):
        self._ran(test)
        super().addSuccess(test)

    def addFailure(self, test, err):
        self._ran(test)
        super().addFailure(test, err)

    def addError(self, test, err):
        self._ran(test)
        super().addError(test, err)

    def addExpectedFailure(self, test, err):
        self._ran(test)
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._ran(test)
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        self._ran(test)
        super().addSubTest(test, subtest, err)


def main(argv: list) -> int:
    if len(argv) != 2:
        print("usage: run-unit-tests.py TEST_DIR", file=sys.stderr)
        return 2
    # Match `python3 -m unittest`, which puts the current directory, not this
    # script's directory, first on the import path.
    sys.path[0] = os.getcwd()
    loader = unittest.TestLoader()
    suite = loader.discover(argv[1])
    result = unittest.TextTestRunner(verbosity=1, resultclass=CountingResult).run(suite)
    if loader.errors:
        print(f"error: {len(loader.errors)} test module(s) failed to load", file=sys.stderr)
        return 1
    if not result.executed:
        print("error: no test was executed (none discovered, or all skipped)", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
