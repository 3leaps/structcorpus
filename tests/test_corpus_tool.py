"""Tests for tools/corpus.py (standard library unittest; Python 3.9+)."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import corpus  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ATTRS = (
    b"* text=auto\n"
    b"/fixtures/** -text -filter -ident -working-tree-encoding\n"
    b"/expected/** -text -filter -ident -working-tree-encoding\n"
    b"/manifests/**/*.jsonl -text -filter -ident -working-tree-encoding\n"
)


RULE = b" -text -filter -ident -working-tree-encoding"
PATTERNS = (b"/fixtures/**", b"/expected/**", b"/manifests/**/*.jsonl")
GIT = shutil.which("git")
PROTECTED_PATHS = (
    "fixtures/yaml/a.yaml",
    "expected/yaml/a.json",
    "manifests/cases.jsonl",
    "manifests/yaml/cases.jsonl",
)
PROTECTED_ATTRS = ("text", "filter", "ident", "working-tree-encoding")

ACCEPTED_ATTRS = (
    ATTRS,
    b"*.md text eol=lf\n" + ATTRS,
    ATTRS + b"*.png -diff\n*.bin -text binary\n*.jsonl -text\n",
    ATTRS.replace(b"-working-tree-encoding\n", b"-working-tree-encoding -diff\n"),
    ATTRS.replace(b"\n", b"\r\n"),
    b"# comment\n\n  # indented comment\n" + ATTRS.replace(b" -text", b"\t-text"),
)


def attribute_variants():
    """(pattern, name, .gitattributes bytes, whether git itself loses the protection) per rejected variant."""
    for pattern in PATTERNS:
        base = b"".join(line + b"\n" for line in ATTRS.splitlines() if not line.startswith(pattern + b" "))
        yield from (
            (pattern, name, data, loses)
            for name, data, loses in (
                ("commented out", base + b"# " + pattern + RULE + b"\n", True),
                ("narrower scope", base + b"/nested" + pattern + RULE + b"\n", True),
                ("same-line override", base + pattern + RULE + b" text=auto\n", True),
                ("inline comment", base + pattern + RULE + b" # byte exact\n", True),
                ("double dash", base + pattern + RULE + b" --text\n", True),
                ("lone bang", base + pattern + RULE + b" !\n", True),
                ("lone dash", base + pattern + RULE + b" -\n", True),
                (
                    "nbsp separator",
                    base + pattern + RULE.replace(b" -working", "\u00a0-working".encode()) + b"\n",
                    True,
                ),
                ("bare cr", base + b"# note\r" + pattern + RULE + b"\n", True),
                ("long line", base + pattern + RULE + b" " * 3000 + b"\n", True),
                ("later override", ATTRS + b"* text=auto\n", True),
                ("later unspecify", ATTRS + b"* !text\n", True),
                ("later filter", ATTRS + b"* filter=lfs\n", True),
                ("macro", b"[attr]conv text\n" + ATTRS + pattern + b" conv\n", True),
                ("quoted macro", b'"[attr]conv" text\n' + ATTRS + pattern + b" conv\n", True),
                ("escaped quoted macro", b'"\\133attr]conv" text\n' + ATTRS + pattern + b" conv\n", True),
                ("same-line eol", base + pattern + RULE + b" eol=crlf\n", False),
                ("later legacy crlf", ATTRS + b"* crlf\n", False),
                ("reserved name", base + pattern + RULE + b" builtin_objectmode\n", False),
                ("rule ends in bare cr at eof", base + pattern + RULE + b"\r", False),
                ("comment ends in bare cr at eof", ATTRS + b"# end\r", False),
            )
        )


def isolated_git_env(tmp):
    """An environment that keeps host Git configuration and attribute files out of the oracle."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        HOME=tmp,
        XDG_CONFIG_HOME=tmp,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_ATTR_NOSYSTEM="1",
    )
    return env


def git_protects(data):
    """Whether real git leaves every protected path with all conversion attributes unset."""
    with tempfile.TemporaryDirectory() as tmp:
        env = isolated_git_env(tmp)
        subprocess.run([GIT, "init", "-q", tmp], env=env, check=True)
        with open(os.path.join(tmp, ".gitattributes"), "wb") as fh:
            fh.write(data)
        out = subprocess.run(
            [GIT, "-C", tmp, "check-attr"] + list(PROTECTED_ATTRS) + ["--"] + list(PROTECTED_PATHS),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        ).stdout.decode("utf-8")
    got = {tuple(line.rsplit(": ", 2)) for line in out.splitlines()}
    return got == {(p, a, "unset") for p in PROTECTED_PATHS for a in PROTECTED_ATTRS}


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

    def test_rejects_floats(self):
        for text in (b'{"a": 1.0}', b'{"a": 1e3}', b"[0.5]"):
            with self.assertRaises(ValueError):
                corpus.load_json_strict(text)

    def test_integer_range(self):
        self.assertEqual(corpus.load_json_strict(b"[9007199254740991, -9007199254740991]"), [2**53 - 1, -(2**53 - 1)])
        for text in (b"[9007199254740992]", b"[-9007199254740992]", b'{"a": [1e400]}'):
            with self.assertRaises(ValueError):
                corpus.load_json_strict(text)

    def test_rejects_lone_surrogates(self):
        for text in (b'["\\ud800"]', b'{"\\udc00": 1}', b'["x\\ud83d"]'):
            with self.assertRaises(ValueError):
                corpus.load_json_strict(text)

    def test_accepts_surrogate_pair(self):
        self.assertEqual(corpus.load_json_strict(b'["\\ud83d\\ude00"]'), ["\U0001f600"])

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
        self.assertRejected("must set -text")

    def test_missing_shard_gitattributes_rule(self):
        write(self.root, ".gitattributes", ATTRS.replace(b"/manifests/**/*.jsonl", b"/manifests/*.jsonl"))
        self.assertRejected("/manifests/**/*.jsonl must set -text")

    def test_gitattributes_rules_must_be_active_and_last(self):
        for pattern, name, data, git_loses in attribute_variants():
            with self.subTest(pattern=pattern, variant=name):
                write(self.root, ".gitattributes", data)
                self.assertNotEqual(self.errors(), [])
                if git_loses and GIT:
                    self.assertFalse(git_protects(data), "variant does not defeat git; mark it conservative")

    def test_gitattributes_rules_allow_earlier_and_unrelated_lines(self):
        for data in ACCEPTED_ATTRS:
            with self.subTest(data=data):
                write(self.root, ".gitattributes", data)
                self.assertEqual(self.errors(), [])
                if GIT:
                    self.assertTrue(git_protects(data))

    def test_git_oracle_is_isolated(self):
        env = isolated_git_env("/tmp/x")
        for key, value in (("GIT_ATTR_NOSYSTEM", "1"), ("GIT_CONFIG_NOSYSTEM", "1"), ("GIT_CONFIG_GLOBAL", os.devnull)):
            self.assertEqual(env.get(key), value)
        self.assertEqual(env["HOME"], "/tmp/x")
        self.assertEqual(env["XDG_CONFIG_HOME"], "/tmp/x")
        if GIT:
            self.assertFalse(git_protects(b""))

    @unittest.skipUnless(GIT, "needs git")
    def test_shipped_gitattributes_protect_under_git(self):
        with open(os.path.join(REPO, ".gitattributes"), "rb") as fh:
            self.assertTrue(git_protects(fh.read()))

    def test_gitattributes_text_only_is_insufficient(self):
        write(self.root, ".gitattributes", b"/fixtures/** -text\n/expected/** -text\n")
        self.assertRejected("-filter")

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
        for sub in ("manifests", "fixtures", "recipes", "generators"):
            shutil.copytree(
                os.path.join(REPO, sub), os.path.join(self.root, sub), ignore=shutil.ignore_patterns("__pycache__")
            )
        self.assertEqual(corpus.main(["validate", "--root", self.root]), 0)
        write(self.root, "fixtures/yaml/Bad.yaml", b"x")
        self.assertEqual(corpus.main(["validate", "--root", self.root]), 1)


class TestInvisibleText(unittest.TestCase):
    """Reviewed text holds no raw invisible characters; metadata uses JSON escapes."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, "docs"))
        os.makedirs(os.path.join(self.root, "fixtures", "yaml"))

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        with open(os.path.join(self.root, *rel.split("/")), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def test_rejected_characters(self):
        for code in (
            0x00,
            0x07,
            0x0B,
            0x0C,
            0x1B,
            0x7F,
            0x85,
            0x9F,
            0x061C,
            0x200B,
            0x200F,
            0x2028,
            0x2029,
            0x202E,
            0x2060,
            0x2066,
            0x2069,
            0xFEFF,
        ):
            with self.subTest(code=hex(code)):
                self.write("docs/a.md", "ok\nbad " + chr(code) + " here\n")
                errs = corpus.check_invisible_text(self.root)
                self.assertEqual(errs, ["docs/a.md:2: raw U+%04X; write it as an escape" % code])

    def test_allowed_characters(self):
        self.write("docs/a.md", "tab\there\r\nemdash \u2014 e\u0301 \u00e9 \u20ac \U0001f600\n")
        self.assertEqual(corpus.check_invisible_text(self.root), [])

    def test_fixtures_are_exempt(self):
        self.write("fixtures/yaml/x.yaml", "k: a\u2028b\n")
        self.assertEqual(corpus.check_invisible_text(self.root), [])

    def test_escaped_in_json_is_fine_raw_is_not(self):
        os.makedirs(os.path.join(self.root, "manifests"))
        self.write("manifests/cases.jsonl", '{"v":"a\\u2028b"}\n')
        self.assertEqual(corpus.check_invisible_text(self.root), [])
        self.write("manifests/cases.jsonl", '{"v":"a\u2028b"}\n')
        self.assertEqual(len(corpus.check_invisible_text(self.root)), 1)

    def test_validate_enforces_it(self):
        # The repository check (and so `corpus.py validate`) runs this rule, not only the helper.
        self.write("docs/a.md", "bad \u202e here\n")
        self.assertIn("docs/a.md:1: raw U+202E; write it as an escape", corpus.check_repository(self.root))

    def test_shipped_tree_is_clean(self):
        self.assertEqual(corpus.check_invisible_text(REPO), [])

    def test_cache_substring_does_not_exempt_reviewed_text(self):
        self.write("docs/about-__pycache__.md", "bad \u202e here\n")
        self.assertEqual(
            corpus.check_invisible_text(self.root), ["docs/about-__pycache__.md:1: raw U+202E; write it as an escape"]
        )


if __name__ == "__main__":
    unittest.main()
