#!/usr/bin/env python3
"""Run the unit tests under TEST_DIR; fail unless at least one test body ran.

Equivalent to ``python3 -m unittest discover -s TEST_DIR`` from the current
directory, but the exit status also requires at least one executed (not skipped) test
and no discovery errors: on Python 3.9 to 3.11, unittest exits 0 when discovery finds
no tests. Standard library only (Python 3.9+).

Usage: run-unit-tests.py TEST_DIR
"""

import os
import sys
import unittest


def main(argv: list) -> int:
    if len(argv) != 2:
        print("usage: run-unit-tests.py TEST_DIR", file=sys.stderr)
        return 2
    # Match `python3 -m unittest`, which puts the current directory, not this
    # script's directory, first on the import path.
    sys.path[0] = os.getcwd()
    loader = unittest.TestLoader()
    suite = loader.discover(argv[1])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if loader.errors:
        print(f"error: {len(loader.errors)} test module(s) failed to load", file=sys.stderr)
        return 1
    executed = result.testsRun - len(result.skipped)
    if executed <= 0:
        print("error: no test was executed (none discovered, or all skipped)", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
