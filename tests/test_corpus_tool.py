"""Tests for tools/corpus.py (standard library unittest; Python 3.9+)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import corpus  # noqa: E402

ATTRS = b"* text=auto\n/fixtures/** -text\n/expected/** -text\n"


def write(root, rel, data):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        write(self.root, ".gitattributes", ATTRS)

    def tearDown(self):
        self._tmp.cleanup()

    def errors(self):
        return corpus.check_repository(self.root)

    def assertRejected(self, needle):
        errs = self.errors()
        self.assertTrue(any(needle in e for e in errs), "expected %r in %r" % (needle, errs))


class TestStrictJson(unittest.TestCase):
    def test_rejects_duplicate_keys(self):
        with self.assertRaises(corpus.DuplicateKeyError):
            corpus.load_json_strict(b'{"id": "a", "id": "b"}')

    def test_rejects_duplicate_nested_keys(self):
        with self.assertRaises(corpus.DuplicateKeyError):
            corpus.load_json_strict(b'{"a": {"k": 1, "k": 1}}')

    def test_rejects_nonfinite(self):
        for text in (b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}'):
            with self.assertRaises(ValueError):
                corpus.load_json_strict(text)

    def test_accepts_plain(self):
        self.assertEqual(corpus.load_json_strict(b'{"a": [1, "x"]}'), {"a": [1, "x"]})


class TestPaths(unittest.TestCase):
    def test_accepts_portable(self):
        self.assertEqual(corpus.path_problems("fixtures/yaml/bool-core-001.yaml"), [])

    def test_rejects_unportable(self):
        for rel in (
            "fixtures/yaml/Upper.yaml",
            "fixtures/yaml/has space.yaml",
            "fixtures/yaml/trailing.",
            "fixtures/yaml/con.yaml",
            "fixtures/yaml/lpt1",
            "fixtures/yaml/-leading-dash.yaml",
            "fixtures/yaml/" + "a" * 200,
        ):
            self.assertTrue(corpus.path_problems(rel), rel)


class TestRepositoryRules(RepoCase):
    def test_clean_repository(self):
        write(self.root, "fixtures/yaml/ok.yaml", b"a: 1\r\n")
        self.assertEqual(self.errors(), [])

    def test_missing_gitattributes_rule(self):
        write(self.root, ".gitattributes", b"* text=auto\n")
        self.assertRejected("must be marked -text")

    def test_staging_directory(self):
        write(self.root, "fixtures/unknown/x.yaml", b"a: 1\n")
        self.assertRejected("intake/staging")

    def test_oversize_fixture(self):
        write(self.root, "fixtures/yaml/big.yaml", b"a" * (corpus.MAX_FIXTURE_BYTES + 1))
        self.assertRejected("per file")

    def test_unportable_name(self):
        write(self.root, "fixtures/yaml/Bad.yaml", b"x")
        self.assertRejected("not lowercase")

    def test_duplicate_key_in_manifest(self):
        write(self.root, "manifests/cases.jsonl", b'{"id": "a"}\n{"id": "b", "id": "c"}\n')
        self.assertRejected("manifests/cases.jsonl:2: duplicate JSON key")

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "symlinks unavailable")
    def test_symlink(self):
        write(self.root, "fixtures/yaml/target.yaml", b"x")
        os.symlink("target.yaml", os.path.join(self.root, "fixtures", "yaml", "link.yaml"))
        self.assertRejected("symbolic links")

    def test_cli_exit_codes(self):
        self.assertEqual(corpus.main(["validate", "--root", self.root]), 0)
        write(self.root, "fixtures/yaml/Bad.yaml", b"x")
        self.assertEqual(corpus.main(["validate", "--root", self.root]), 1)


if __name__ == "__main__":
    unittest.main()
