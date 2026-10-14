"""Recipe, hydrate, and verify tests (Python 3.9+ stdlib)."""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))

import corpus  # noqa: E402

GEN = '''
def generate(parameters):
    n = parameters["n"]
    size = parameters.get("size", 1)
    for i in range(n):
        yield "r%04d" % i, "scalar-resolution", "k: " + "x" * size + "\\n", {"documents": [{"t": "str", "v": "x"}]}, []
'''


class RecipeRepo(unittest.TestCase):
    """A scratch repository with one small recipe, plus a separate output parent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        self.outdir = os.path.join(self._tmp.name, "out")
        os.makedirs(self.outdir)
        shutil.copytree(os.path.join(REPO, "manifests", "profiles"), os.path.join(self.root, "manifests", "profiles"))
        os.makedirs(os.path.join(self.root, "generators", "yaml"))
        os.makedirs(os.path.join(self.root, "recipes", "yaml"))
        with open(os.path.join(self.root, "generators", "yaml", "tiny.py"), "w") as fh:
            fh.write(GEN)
        template = sorted(n for n in os.listdir(os.path.join(REPO, "recipes", "yaml"))
                          if n.startswith("core-truth-numbers."))[-1]
        with open(os.path.join(REPO, "recipes", "yaml", template)) as fh:
            self.recipe = json.load(fh)
        self.recipe.update(id="tiny", revision=1, generator="generators/yaml/tiny.py", parameters={"n": 5})
        self.recipe["execution"].update(max_cases=10)
        self.pin()

    def tearDown(self):
        self._tmp.cleanup()

    def path(self):
        return os.path.join(self.root, "recipes", "yaml", "tiny.r1.json")

    def save(self):
        with open(self.path(), "w") as fh:
            json.dump(self.recipe, fh)

    def pin(self):
        """Record the expected counts and digest from a dry generation."""
        self.recipe["expected"] = {"cases": 1, "input_bytes": 0, "digest": "sha256:" + "0" * 64}
        lines, nbytes = [], 0
        for _, data, rec, _line in corpus._recipe_cases(self.root, "recipes/yaml/tiny.r1.json", self.recipe):
            lines.append(corpus.canonical_json(rec).encode())
            nbytes += len(data)
        self.recipe["expected"] = {"cases": len(lines), "input_bytes": nbytes, "digest": corpus.recipe_digest(lines)}
        self.save()

    def pin_to(self, path):
        rel = os.path.relpath(path, self.root).replace(os.sep, "/")
        self.recipe["expected"] = {"cases": 1, "input_bytes": 0, "digest": "sha256:" + "0" * 64}
        lines, nbytes = [], 0
        for _, data, rec, _line in corpus._recipe_cases(self.root, rel, self.recipe):
            lines.append(corpus.canonical_json(rec).encode())
            nbytes += len(data)
        self.recipe["expected"] = {"cases": len(lines), "input_bytes": nbytes, "digest": corpus.recipe_digest(lines)}
        with open(path, "w") as fh:
            json.dump(self.recipe, fh)

    def out(self, name="h"):
        return os.path.join(self.outdir, name)

    def leftovers(self):
        return [n for n in os.listdir(self.outdir) if n.startswith(".structcorpus-")]

    def assertRefused(self, needle, tier="smoke", out=None):
        out = out or self.out()
        with self.assertRaises(corpus.HydrateError) as ctx:
            corpus.hydrate(self.root, out, tier)
        self.assertIn(needle, str(ctx.exception))
        self.assertFalse(os.path.exists(out) and out.startswith(self.outdir), "partial output left at %s" % out)
        self.assertEqual(self.leftovers(), [])


class TestHydrate(RecipeRepo):
    def test_hydrate_and_verify(self):
        summary = corpus.hydrate(self.root, self.out(), "smoke")
        self.assertEqual(summary["recipes"][0]["cases"], 5)
        self.assertEqual(corpus.verify(self.root, self.out()), [])
        self.assertEqual(self.leftovers(), [])

    def test_two_hydrations_identical(self):
        corpus.hydrate(self.root, self.out("a"), "smoke")
        corpus.hydrate(self.root, self.out("b"), "smoke")
        for dirpath, _, files in os.walk(self.out("a")):
            for name in files:
                a = os.path.join(dirpath, name)
                b = os.path.join(self.out("b"), os.path.relpath(a, self.out("a")))
                with open(a, "rb") as fa, open(b, "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(), name)

    def test_manifest_lines_are_canonical_cases(self):
        corpus.hydrate(self.root, self.out(), "smoke")
        with open(os.path.join(self.out(), "cases.jsonl"), "rb") as fh:
            for line in fh.read().splitlines():
                rec = corpus.load_json_strict(line)
                self.assertEqual(corpus.canonical_json(rec).encode(), line)
                self.assertEqual(rec["classifiers"], {"sensitivity": "0-public", "access-tier": "public"})
                self.assertEqual(rec["input"]["recipe"], "recipes/yaml/tiny.r1.json")

    def test_failed_publication_leaves_nothing(self):
        real = corpus.os.rename

        def boom(src, dst):
            raise OSError("injected rename failure")

        corpus.os.rename = boom
        try:
            with self.assertRaises(OSError):
                corpus.hydrate(self.root, self.out(), "smoke")
        finally:
            corpus.os.rename = real
        self.assertFalse(os.path.exists(self.out()))
        self.assertEqual(self.leftovers(), [])

    def test_refuses_existing_output(self):
        os.makedirs(self.out())
        with self.assertRaises(corpus.HydrateError) as ctx:
            corpus.hydrate(self.root, self.out(), "smoke")
        self.assertIn("already exists", str(ctx.exception))

    def test_refuses_output_inside_checkout(self):
        self.assertRefused("outside the checkout", out=os.path.join(self.root, "build"))

    def test_refuses_checkout_inside_output(self):
        # A not-yet-existing output path that would contain the checkout.
        root = os.path.join(self._tmp.name, "nest", "repo")
        os.makedirs(os.path.dirname(root))
        os.rename(self.root, root)
        with self.assertRaises(corpus.HydrateError) as ctx:
            corpus.hydrate(root, os.path.join(self._tmp.name, "nest"), "smoke")
        self.assertIn("outside the checkout", str(ctx.exception))
        os.rename(root, self.root)

    def test_digest_mismatch(self):
        self.recipe["parameters"]["n"] = 6
        self.save()
        self.assertRefused("does not match recorded")

    def test_max_cases_exceeded(self):
        self.recipe["parameters"]["n"] = 11
        self.save()
        self.assertRefused("max_cases")

    def test_max_output_bytes_exceeded(self):
        self.recipe["parameters"]["size"] = 100
        self.recipe["execution"]["max_output_bytes"] = 200
        self.save()
        self.assertRefused("max_output_bytes")

    def test_recipe_cap_counts_manifest_bytes(self):
        # Inputs alone fit the recipe cap; inputs plus manifest lines do not.
        inputs = self.recipe["expected"]["input_bytes"]
        self.recipe["execution"]["max_output_bytes"] = inputs + 10
        self.save()
        self.assertRefused("max_output_bytes")

    def test_tier_aggregate_cap(self):
        # Each of two recipes fits the tier on its own; together they exceed it.
        first = copy.deepcopy(self.recipe)
        self.recipe.update(id="tiny2")
        self.save_as = os.path.join(self.root, "recipes", "yaml", "tiny2.r1.json")
        self.pin_to(self.save_as)
        per_recipe = sum(len(d) + len(l) + 1 for _, d, _r, l in
                         corpus._recipe_cases(self.root, "recipes/yaml/tiny2.r1.json", self.recipe))
        saved = corpus.TIER_CAPS["smoke"]
        cap = per_recipe + per_recipe // 2  # one recipe fits; two do not
        corpus.TIER_CAPS["smoke"] = cap
        for doc, path in ((first, self.path()), (self.recipe, self.save_as)):
            doc["execution"]["max_output_bytes"] = cap
            with open(path, "w") as fh:
                json.dump(doc, fh)
        try:
            self.assertEqual(corpus.check_recipes(self.root), [])
            self.assertLess(per_recipe, cap)
            self.assertRefused("aggregate output exceeds")
        finally:
            corpus.TIER_CAPS["smoke"] = saved

    def test_higher_tier_recipe_excluded(self):
        self.recipe["execution"]["tier"] = "conformance"
        self.save()
        self.assertEqual(corpus.hydrate(self.root, self.out(), "smoke")["recipes"], [])

    def test_repeated_id(self):
        with open(os.path.join(self.root, "generators", "yaml", "tiny.py"), "a") as fh:
            fh.write("\n_g = generate\ndef generate(p):\n    for r in _g(p):\n        yield ('same',) + r[1:]\n")
        self.assertRefused("repeated id")


class TestVerify(RecipeRepo):
    def setUp(self):
        RecipeRepo.setUp(self)
        corpus.hydrate(self.root, self.out(), "smoke")

    def input_file(self):
        top = os.path.join(self.out(), "inputs", "yaml", "tiny")
        return os.path.join(top, sorted(os.listdir(top))[0])

    def test_changed_input(self):
        with open(self.input_file(), "ab") as fh:
            fh.write(b"\r")
        self.assertTrue(any("does not match manifest" in e for e in corpus.verify(self.root, self.out())))

    def test_missing_input(self):
        os.unlink(self.input_file())
        self.assertTrue(any("input missing" in e for e in corpus.verify(self.root, self.out())))

    def test_missing_marker(self):
        os.unlink(os.path.join(self.out(), corpus.HYDRATE_MARKER))
        self.assertTrue(any("not a completed hydration" in e for e in corpus.verify(self.root, self.out())))

    def test_noncanonical_manifest(self):
        path = os.path.join(self.out(), "cases.jsonl")
        with open(path, "rb") as fh:
            lines = fh.read().splitlines()
        lines[0] = json.dumps(json.loads(lines[0]), indent=1).replace("\n", "").encode()
        with open(path, "wb") as fh:
            fh.write(b"\n".join(lines) + b"\n")
        self.assertTrue(any("not canonical" in e for e in corpus.verify(self.root, self.out())))

    def test_changed_expectation(self):
        path = os.path.join(self.out(), "cases.jsonl")
        with open(path, "rb") as fh:
            lines = fh.read().splitlines()
        rec = json.loads(lines[0])
        rec["expectations"]["value"][0]["documents"][0]["v"] = "y"
        lines[0] = corpus.canonical_json(rec).encode()
        with open(path, "wb") as fh:
            fh.write(b"\n".join(lines) + b"\n")
        self.assertTrue(any("expected digest" in e for e in corpus.verify(self.root, self.out())))

    def edit_marker(self, fn):
        path = os.path.join(self.out(), corpus.HYDRATE_MARKER)
        with open(path, "rb") as fh:
            summary = json.loads(fh.read())
        fn(summary)
        with open(path, "wb") as fh:
            fh.write(corpus.canonical_json(summary).encode())

    def change_first_expectation(self):
        path = os.path.join(self.out(), "cases.jsonl")
        with open(path, "rb") as fh:
            lines = fh.read().splitlines()
        rec = json.loads(lines[0])
        rec["expectations"]["value"][0]["documents"][0]["v"] = "y"
        lines[0] = corpus.canonical_json(rec).encode()
        with open(path, "wb") as fh:
            fh.write(b"\n".join(lines) + b"\n")

    def test_cleared_marker_recipes_cannot_hide_changes(self):
        self.change_first_expectation()
        self.edit_marker(lambda s: s.update(recipes=[]))
        self.assertTrue(any("expected digest" in e or "not listed" in e for e in corpus.verify(self.root, self.out())))

    def test_marker_recipe_removed_cannot_hide_changes(self):
        self.change_first_expectation()
        self.edit_marker(lambda s: s.pop("recipes"))
        self.assertNotEqual(corpus.verify(self.root, self.out()), [])

    def test_manifest_recipe_unknown_to_checkout(self):
        path = os.path.join(self.out(), "cases.jsonl")
        with open(path, "rb") as fh:
            lines = fh.read().splitlines()
        rec = json.loads(lines[0])
        rec["input"]["recipe"] = "recipes/yaml/forged.r1.json"
        lines[0] = corpus.canonical_json(rec).encode()
        with open(path, "wb") as fh:
            fh.write(b"\n".join(lines) + b"\n")
        self.assertTrue(any("forged" in e for e in corpus.verify(self.root, self.out())))

    def test_marker_lists_recipe_with_no_cases(self):
        self.edit_marker(lambda s: s["recipes"].append({"recipe": "recipes/yaml/tiny.r1.json"}))
        self.assertNotEqual(corpus.verify(self.root, self.out()), [])

    def test_emptied_manifest_and_marker(self):
        with open(os.path.join(self.out(), "cases.jsonl"), "wb"):
            pass
        self.edit_marker(lambda s: s.update(recipes=[]))
        self.assertTrue(any("no cases" in e for e in corpus.verify(self.root, self.out())))

    def test_dropped_case(self):
        path = os.path.join(self.out(), "cases.jsonl")
        with open(path, "rb") as fh:
            lines = fh.read().splitlines()
        with open(path, "wb") as fh:
            fh.write(b"\n".join(lines[1:]) + b"\n")
        self.assertTrue(any("expected digest" in e for e in corpus.verify(self.root, self.out())))


class TestRecipeValidation(RecipeRepo):
    def errors(self):
        return corpus.check_recipes(self.root)

    def assertRejected(self, needle):
        errs = self.errors()
        self.assertTrue(any(needle in e for e in errs), "expected %r in %r" % (needle, errs))

    def test_valid(self):
        self.assertEqual(self.errors(), [])

    def test_classifier(self):
        self.recipe["classifiers"]["sensitivity"] = "2-blinded"
        self.save()
        self.assertRejected("classifiers must be exactly")

    def test_origin(self):
        self.recipe["provenance"]["origin"] = "public-source"
        self.save()
        self.assertRejected("recipes are synthetic")

    def test_unknown_profile(self):
        self.recipe["profile_revision"] = 9
        self.save()
        self.assertRejected("unknown profile")

    def test_missing_generator(self):
        self.recipe["generator"] = "generators/yaml/absent.py"
        self.save()
        self.assertRejected("missing or misplaced")

    def test_generator_outside_tree(self):
        # The file exists, so only the generators/<format>/ prefix rule can reject it.
        os.makedirs(os.path.join(self.root, "tools"))
        shutil.copy(os.path.join(self.root, "generators", "yaml", "tiny.py"), os.path.join(self.root, "tools", "tiny.py"))
        self.recipe["generator"] = "tools/tiny.py"
        self.save()
        self.assertRejected("missing or misplaced")

    def test_generator_unportable_name(self):
        # The file exists under the right prefix; only the portable-name rule can reject it.
        shutil.copy(os.path.join(self.root, "generators", "yaml", "tiny.py"),
                    os.path.join(self.root, "generators", "yaml", "con.py"))
        self.recipe["generator"] = "generators/yaml/con.py"
        self.save()
        self.assertRejected("missing or misplaced")

    def test_output_cap_over_tier(self):
        self.recipe["execution"]["max_output_bytes"] = corpus.TIER_CAPS["smoke"] + 1
        self.save()
        self.assertRejected("tier cap")

    def test_cases_over_max(self):
        self.recipe["execution"]["max_cases"] = 4
        self.save()
        self.assertRejected("must not exceed")

    def test_reviewer_distinct(self):
        self.recipe["review"].update(status="reviewed", reviewer=self.recipe["review"]["author"])
        self.save()
        self.assertRejected("reviewer distinct")

    def test_path_must_match_id(self):
        os.rename(self.path(), os.path.join(self.root, "recipes", "yaml", "other.json"))
        self.assertRejected("path must be recipes/yaml/tiny.r1.json")

    def test_schema_version(self):
        self.recipe["schema_version"] = "recipe/v2"
        self.save()
        self.assertRejected("unsupported schema_version")


class TestShippedRecipes(unittest.TestCase):
    def test_shipped_recipes_validate(self):
        self.assertEqual(corpus.check_recipes(REPO), [])

    def test_smoke_hydration_matches_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "smoke")
            summary = corpus.hydrate(REPO, out, "smoke")
            self.assertTrue(summary["recipes"])
            self.assertEqual(corpus.verify(REPO, out), [])


if __name__ == "__main__":
    unittest.main()
