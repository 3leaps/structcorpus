"""Profile limits, recipe hazards and budgets, and the list command (Python 3.9+ stdlib)."""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import corpus  # noqa: E402

LIMITS_PROFILE = "manifests/profiles/yamlprims-core-limits.r1.json"


class TestProfileLimits(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO, LIMITS_PROFILE)) as fh:
            self.prof = json.load(fh)

    def errors(self, prof):
        errs = []
        corpus.check_profile_limits("p", prof, errs)
        return errs

    def test_shipped_limits_profile_is_valid(self):
        self.assertEqual(self.errors(self.prof), [])
        self.assertEqual(set(self.prof["limits"]), set(corpus.LIMIT_FIELDS))

    def test_profile_without_limits_is_fine(self):
        self.prof.pop("limits")
        self.assertEqual(self.errors(self.prof), [])

    def test_missing_field(self):
        self.prof["limits"].pop("max_depth")
        self.assertTrue(any("exactly" in e for e in self.errors(self.prof)))

    def test_unknown_field(self):
        self.prof["limits"]["max_magic"] = 1
        self.assertTrue(any("exactly" in e for e in self.errors(self.prof)))

    def test_zero_limit(self):
        self.prof["limits"]["max_nodes"] = 0
        self.assertTrue(any(">= 1" in e for e in self.errors(self.prof)))

    def test_bool_is_not_an_integer(self):
        self.prof["limits"]["max_nodes"] = True
        self.assertTrue(any(">= 1" in e for e in self.errors(self.prof)))

    def test_depth_ceiling(self):
        self.prof["limits"]["max_depth"] = 256
        self.assertTrue(any("max_depth must be <= 255" in e for e in self.errors(self.prof)))

    def test_scalar_and_key_within_owned(self):
        for k in ("max_scalar_bytes", "max_key_bytes"):
            prof = json.loads(json.dumps(self.prof))
            prof["limits"][k] = prof["limits"]["max_owned_bytes"] + 1
            self.assertTrue(any("%s must be <= max_owned_bytes" % k in e for e in self.errors(prof)), k)


class Scratch(unittest.TestCase):
    """A disposable copy of the corpus with an output parent outside it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        for d in ("manifests", "recipes", "generators", "fixtures"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(self.root, d))
        shutil.copy(os.path.join(REPO, ".gitattributes"), self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def add_stress_recipe(self, hazards=("deep-nesting",), budgets=None):
        with open(os.path.join(self.root, "recipes", "yaml", "core-truth-numbers.r2.json")) as fh:
            doc = json.load(fh)
        doc.update(id="probe-stress", revision=1)
        ex = doc["execution"]
        ex.update(tier="stress", max_output_bytes=corpus.TIER_CAPS["stress"], hazards=list(hazards))
        if budgets is not None:
            ex["budgets"] = budgets
        rel = "recipes/yaml/probe-stress.r1.json"
        doc["expected"] = {"cases": 1, "input_bytes": 0, "digest": "sha256:" + "0" * 64}
        lines, nb = [], 0
        for _, d, _rec, line in corpus._recipe_cases(self.root, rel, doc):
            lines.append(line)
            nb += len(d)
        doc["expected"] = {"cases": len(lines), "input_bytes": nb, "digest": corpus.recipe_digest(lines)}
        with open(os.path.join(self.root, rel), "w") as fh:
            json.dump(doc, fh)
        return rel, lines


BUDGETS = {"wall_ms": 2000, "memory_bytes": 268435456, "output_bytes": 65536}


class TestLimitsWiredIntoValidate(Scratch):
    def test_validate_rejects_invalid_limits_profile_on_disk(self):
        path = os.path.join(self.root, LIMITS_PROFILE)
        with open(path) as fh:
            prof = json.load(fh)
        prof["limits"]["max_depth"] = 999
        with open(path, "w") as fh:
            json.dump(prof, fh)
        errs = corpus.check_manifests(self.root)
        self.assertTrue(any("yamlprims-core-limits.r1.json: max_depth must be <= 255" in e for e in errs), errs)


class TestRecipeHazards(Scratch):
    def test_hazards_require_budgets(self):
        self.add_stress_recipe(budgets=None)
        self.assertTrue(any("must declare per-case budgets" in e for e in corpus.check_recipes(self.root)))

    def test_hazards_with_budgets_valid(self):
        self.add_stress_recipe(budgets=BUDGETS)
        self.assertEqual(corpus.check_recipes(self.root), [])

    def test_cases_inherit_tier_hazards_and_budgets(self):
        _, lines = self.add_stress_recipe(budgets=BUDGETS)
        ex = json.loads(lines[0])["execution"]
        self.assertEqual(ex, {"tier": "stress", "hazards": ["deep-nesting"], "budgets": BUDGETS})

    def test_recipes_without_hazards_keep_their_records(self):
        # Smoke and conformance recipes declare no hazards, so their generated records (and digests)
        # are unchanged by the hazards field. Hazardous recipes are stress-tier ladders only.
        for rel, doc in corpus.load_recipes(REPO, []).items():
            if doc["execution"]["tier"] == "stress":
                self.assertTrue(doc["execution"].get("hazards"), rel)
                continue
            self.assertNotIn("hazards", doc["execution"], rel)
            self.assertNotIn("budgets", doc["execution"], rel)

    def test_stress_excluded_below_stress_tier(self):
        self.add_stress_recipe(budgets=BUDGETS)
        out = os.path.join(self._tmp.name, "smoke")
        summary = corpus.hydrate(self.root, out, "smoke")
        self.assertNotIn("recipes/yaml/probe-stress.r1.json", [r["recipe"] for r in summary["recipes"]])

    def test_stress_tier_with_no_stress_recipes(self):
        # Drop the two large conformance tables from the scratch copy; the property under test is
        # that a stress hydration with no stress recipes completes and verifies.
        for big in ("core-truth-booleans.r2.json", "core-truth-collisions.r1.json"):
            os.remove(os.path.join(self.root, "recipes", "yaml", big))
        for name in os.listdir(os.path.join(self.root, "recipes", "yaml")):
            if name.startswith("ladder-"):
                os.remove(os.path.join(self.root, "recipes", "yaml", name))
        out = os.path.join(self._tmp.name, "stress")
        corpus.hydrate(self.root, out, "stress")
        self.assertEqual(corpus.verify(self.root, out), [])

    def test_shipped_stress_ladders_hydrate_and_verify(self):
        ladders = {
            corpus.load_json_strict(open(os.path.join(REPO, "recipes", "yaml", n), "rb").read())["id"]
            for n in os.listdir(os.path.join(REPO, "recipes", "yaml"))
            if n.startswith("ladder-")
        }
        self.assertEqual(len(ladders), 5)
        out = os.path.join(self._tmp.name, "ladders")
        summary = corpus.hydrate(REPO, out, "stress", ladders)
        self.assertEqual({r["recipe"].split("/")[-1].split(".")[0] for r in summary["recipes"]}, ladders)
        self.assertEqual(corpus.verify(REPO, out), [])


class TestList(Scratch):
    def rows(self, tier, show=False):
        return corpus.list_entries(self.root, tier, show)

    def test_tier_filter(self):
        self.add_stress_recipe(budgets=BUDGETS)
        names = lambda tier: {r["name"] for r in self.rows(tier)}  # noqa: E731
        self.assertNotIn("recipes/yaml/probe-stress.r1.json", names("conformance"))
        self.assertIn("recipes/yaml/probe-stress.r1.json", names("stress"))
        self.assertTrue(names("smoke") < names("conformance") <= names("stress"))

    def test_counts_match_recipes_and_cases(self):
        rows = self.rows("conformance")
        with open(os.path.join(self.root, "manifests", "cases.jsonl"), "rb") as fh:
            committed = sum(1 for line in fh.read().splitlines() if line.strip())
        self.assertEqual(sum(1 for r in rows if r["kind"] == "case"), committed)
        for r in rows:
            if r["kind"] == "recipe":
                with open(os.path.join(self.root, r["name"])) as fh:
                    self.assertEqual(r["cases"], json.load(fh)["expected"]["cases"])

    def test_show_budgets_reports_true_output(self):
        rows = self.rows("smoke", show=True)
        for r in rows:
            if r["kind"] == "recipe":
                self.assertLessEqual(r["output_bytes"], r["max_output_bytes"], r["name"])
                self.assertGreater(r["output_bytes"], r["input_bytes"], r["name"])

    def test_json_is_canonical(self):
        args = type("A", (), {"root": self.root, "tier": "smoke", "show_budgets": False, "json": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(corpus.cmd_list(args), 0)
        text = buf.getvalue().rstrip("\n")
        self.assertEqual(corpus.canonical_json(corpus.load_json_strict(text.encode())), text)


if __name__ == "__main__":
    unittest.main()
