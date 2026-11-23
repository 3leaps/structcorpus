#!/usr/bin/env bash
# Controls for scripts/run-unit-tests.py with real Python: every python3 found
# (here the 3.9 floor and the current interpreter) must accept non-vacuous
# passing suites and refuse vacuous, failing, or never-run ones.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
runner="$root/scripts/run-unit-tests.py"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

H='import unittest\n\n\n'
P="${H}class T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
mk() { # mk CASE CONTENT [SECOND_FILE_CONTENT]
  mkdir -p "$scratch/$1/tests"
  printf "$2" >"$scratch/$1/tests/test_a.py"
  [[ -z "${3:-}" ]] || printf "$3" >"$scratch/$1/tests/test_b.py"
}
accept=(pass mixed subskip classskip modskip xfail asyncpass dupid roprop customrun)
refuse=(zero allskip onlyclassskip setupsub bodysub cleanupsub fixturecall modfixturecall
  asyncfail gen agen corosync fail subfail usucc importerr)
mk pass "$P"
mk mixed "${P}\n    @unittest.skip(\"x\")\n    def test_s(self):\n        pass\n"
mk subskip "${P}\n    def test_sub(self):\n        with self.subTest(i=1):\n            self.skipTest(\"x\")\n"
mk classskip "${P}\n\nclass S(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        raise unittest.SkipTest(\"x\")\n\n    def test_n(self):\n        pass\n"
mk modskip "$P" "${H}def setUpModule():\n    raise unittest.SkipTest(\"x\")\n\n\nclass S(unittest.TestCase):\n    def test_n(self):\n        pass\n"
mk xfail "${H}class T(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_x(self):\n        self.fail(\"x\")\n"
mk asyncpass "${H}class T(unittest.IsolatedAsyncioTestCase):\n    async def test_a(self):\n        pass\n"
mk dupid "${H}class T(unittest.TestCase):\n    def __init__(self, name, skip=False):\n        super().__init__(name)\n        self.skip = skip\n\n    def test_p(self):\n        if self.skip:\n            self.skipTest(\"x\")\n\n\ndef load_tests(loader, tests, pattern):\n    return unittest.TestSuite([T(\"test_p\"), T(\"test_p\", True)])\n"
mk roprop "${H}class T(unittest.TestCase):\n    def _impl(self):\n        pass\n\n    @property\n    def test_p(self):\n        return self._impl\n\n\ndef load_tests(loader, tests, pattern):\n    return unittest.TestSuite([T(\"test_p\")])\n"
mk customrun "${H}class T(unittest.TestCase):\n    def run(self, result=None):\n        self.test_p = self.test_p\n        return super().run(result)\n\n    def test_p(self):\n        pass\n"
mk zero '# no tests\n'
mk allskip "${H}class T(unittest.TestCase):\n    @unittest.skip(\"x\")\n    def test_s(self):\n        pass\n"
mk onlyclassskip "${H}class S(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        raise unittest.SkipTest(\"x\")\n\n    def test_n(self):\n        pass\n"
mk setupsub "${H}class T(unittest.TestCase):\n    def setUp(self):\n        with self.subTest(i=1):\n            pass\n        self.skipTest(\"x\")\n\n    def test_n(self):\n        pass\n"
mk bodysub "${H}class T(unittest.TestCase):\n    def test_x(self):\n        with self.subTest(i=1):\n            pass\n        self.skipTest(\"x\")\n"
mk cleanupsub "${H}class T(unittest.TestCase):\n    def setUp(self):\n        def c():\n            with self.subTest(i=2):\n                pass\n\n        self.addCleanup(c)\n        self.skipTest(\"x\")\n\n    def test_n(self):\n        pass\n"
mk fixturecall "${H}class T(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        cls(\"test_n\").test_n()\n        raise unittest.SkipTest(\"x\")\n\n    def test_n(self):\n        pass\n"
mk modfixturecall "${H}def setUpModule():\n    T(\"test_n\").test_n()\n    raise unittest.SkipTest(\"x\")\n\n\nclass T(unittest.TestCase):\n    def test_n(self):\n        pass\n"
mk asyncfail "${H}class T(unittest.IsolatedAsyncioTestCase):\n    async def test_a(self):\n        self.fail(\"x\")\n"
mk gen "${H}class T(unittest.TestCase):\n    def test_g(self):\n        yield 1\n"
mk agen "${H}class T(unittest.TestCase):\n    async def test_g(self):\n        yield 1\n"
mk corosync "${H}class T(unittest.TestCase):\n    async def test_c(self):\n        self.fail(\"x\")\n"
mk fail "${H}class T(unittest.TestCase):\n    def test_x(self):\n        self.fail(\"x\")\n"
mk subfail "${H}class T(unittest.TestCase):\n    def test_sub(self):\n        with self.subTest(i=1):\n            self.fail(\"x\")\n"
mk usucc "${H}class T(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_x(self):\n        pass\n"
mk importerr 'import not_a_module_for_this_control\n'

pythons=()
for candidate in "$(command -v python3)" /usr/bin/python3; do
  [[ -x "$candidate" ]] || continue
  for seen in ${pythons[@]+"${pythons[@]}"}; do [[ "$seen" -ef "$candidate" ]] && continue 2; done
  pythons+=("$candidate")
done
[[ "${#pythons[@]}" -gt 0 ]] || {
  echo 'error: no python3 for the unit-test gate controls' >&2
  exit 1
}
for py in "${pythons[@]}"; do
  version="$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  for case in "${accept[@]}" "${refuse[@]}"; do
    want=1
    for a in "${accept[@]}"; do [[ "$a" == "$case" ]] && want=0; done
    rc=0
    (cd "$scratch/$case" && "$py" -B "$runner" tests) >/dev/null 2>&1 || rc=$?
    [[ "$rc" == "$want" ]] || {
      echo "error: run-unit-tests on Python $version: $case exited $rc, expected $want" >&2
      exit 1
    }
  done
  echo "[ok] run-unit-tests on Python $version: ${#accept[@]} non-vacuous suites accepted, ${#refuse[@]} vacuous, failing or never-run suites refused"
done
