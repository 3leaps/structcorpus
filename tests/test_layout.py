"""Format registry, per-format shards, and the static-case aggregate (DDR-0014; Python 3.9+ stdlib)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))

import corpus  # noqa: E402

SHARD = "manifests/yaml/cases.jsonl"
TESTFMT = {"dialects": ("yaml-1.2.2",), "inventories": ("cases", "fixtures"), "generated_input_extension": ".yaml"}


class LayoutRepo(unittest.TestCase):
    """A disposable copy of every registered corpus tree, plus an output parent outside it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        self.outdir = os.path.join(self._tmp.name, "out")
        os.makedirs(self.outdir)
        os.makedirs(self.root)
        for sub in ("manifests", "fixtures", "recipes", "generators"):
            shutil.copytree(
                os.path.join(REPO, sub), os.path.join(self.root, sub), ignore=shutil.ignore_patterns("__pycache__")
            )
        shutil.copy(os.path.join(REPO, ".gitattributes"), self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def full(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def read(self, rel):
        with open(self.full(rel), "rb") as fh:
            return fh.read()

    def write(self, rel, data):
        os.makedirs(os.path.dirname(self.full(rel)), exist_ok=True)
        with open(self.full(rel), "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))

    def registry(self):
        return json.loads(self.read(corpus.FORMATS_REL))

    def save_registry(self, doc):
        self.write(corpus.FORMATS_REL, json.dumps(doc, indent=2) + "\n")

    def edit_yaml_entry(self, fn):
        doc = self.registry()
        fn(doc["formats"]["yaml"])
        self.save_registry(doc)

    def cases(self, rel=SHARD):
        return [json.loads(line) for line in self.read(rel).splitlines() if line.strip()]

    def save_cases(self, cases, rel=SHARD, aggregate=True):
        self.write(rel, "".join(json.dumps(c, ensure_ascii=True) + "\n" for c in cases))
        if aggregate:
            self.assertEqual(corpus.write_aggregate(self.root)[0], [])

    def errors(self):
        return corpus.check_all(self.root)

    def assertRejected(self, needle, errors=None):
        errs = self.errors() if errors is None else errors
        self.assertTrue(any(needle in e for e in errs), "expected %r in %r" % (needle, errs))


class TestShippedLayout(LayoutRepo):
    def test_shipped_tree_is_valid(self):
        self.assertEqual(self.errors(), [])

    def test_only_yaml_is_registered_and_implemented(self):
        errors = []
        formats = corpus.load_formats(REPO, errors)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(formats), ["yaml"])
        self.assertEqual(sorted(corpus.IMPLEMENTED_FORMATS), ["yaml"])
        for kind, pattern in corpus.INVENTORY_PATHS.items():
            self.assertEqual(formats["yaml"][kind], pattern.format("yaml"))
        self.assertEqual(formats["yaml"]["generated_input_extension"], ".yaml")

    def test_aggregate_equals_regenerated_concatenation(self):
        errors = []
        formats = corpus.load_formats(REPO, errors)
        expected = corpus.build_aggregate(REPO, formats, errors)
        self.assertEqual(errors, [])
        with open(os.path.join(REPO, *corpus.AGGREGATE_REL.split("/")), "rb") as fh:
            aggregate = fh.read()
        with open(os.path.join(REPO, *SHARD.split("/")), "rb") as fh:
            shard = fh.read()
        self.assertEqual(aggregate, expected)
        self.assertEqual(aggregate, shard)  # YAML is the only format, so the aggregate is its shard

    def test_every_declared_inventory_is_consumed(self):
        errors = []
        formats = corpus.load_formats(REPO, errors)
        entry = formats["yaml"]
        self.assertTrue(list(corpus.static_cases(REPO, formats, errors)))
        self.assertTrue(corpus.load_profiles(REPO, entry, errors))
        self.assertTrue(corpus._load_registry(REPO, entry["span_conventions"], "span", errors))
        self.assertTrue(corpus.load_recipes(REPO, errors, formats))
        self.assertEqual(errors, [])

    def test_schema_and_tool_agree_on_members(self):
        with open(os.path.join(REPO, "schemas", "formats.v1.schema.json")) as fh:
            schema = json.load(fh)
        fmt = schema["definitions"]["format"]
        self.assertEqual(sorted(fmt["properties"]), sorted(corpus.FORMAT_MEMBERS))
        self.assertEqual(schema["properties"]["schema_version"]["const"], corpus.SUPPORTED["formats"])
        self.assertEqual(fmt["properties"]["status"]["const"], "active")
        self.assertFalse(fmt["additionalProperties"])
        self.assertFalse(schema["additionalProperties"])


class TestAggregate(LayoutRepo):
    def test_stale_aggregate_extra_record(self):
        self.write(corpus.AGGREGATE_REL, self.read(corpus.AGGREGATE_REL) + self.read(SHARD).splitlines(True)[0])
        self.assertRejected("manifests/cases.jsonl: stale aggregate: 104 lines, the format shards give 103")

    def test_stale_aggregate_missing_record(self):
        cases = self.cases()
        self.save_cases(cases[:-1], aggregate=False)
        self.assertRejected("manifests/cases.jsonl: stale aggregate: 103 lines, the format shards give 102")

    def test_stale_aggregate_changed_record(self):
        cases = self.cases()
        self.save_cases(cases)
        cases[4]["review"]["notes"] = "edited in the shard only"
        before = self.read(corpus.AGGREGATE_REL)
        self.save_cases(cases, aggregate=False)
        self.assertRejected("first difference at line 5")
        self.assertEqual(self.read(corpus.AGGREGATE_REL), before)  # validate never writes

    def test_missing_aggregate(self):
        os.unlink(self.full(corpus.AGGREGATE_REL))
        self.assertRejected("manifests/cases.jsonl: aggregate is missing")

    def test_aggregate_command_regenerates(self):
        cases = self.cases()
        cases[7]["review"]["notes"] = "edited in the shard only"
        self.save_cases(cases, aggregate=False)
        self.assertEqual(corpus.main(["validate", "--root", self.root]), 1)
        self.assertEqual(corpus.main(["aggregate", "--root", self.root]), 0)
        self.assertEqual(self.read(corpus.AGGREGATE_REL), self.read(SHARD))
        self.assertEqual(self.errors(), [])

    def test_shard_must_end_with_lf(self):
        self.write(SHARD, self.read(SHARD).rstrip(b"\n"))
        self.assertRejected("manifests/yaml/cases.jsonl: case shard lines must each end with LF")

    def test_duplicate_id_within_shard(self):
        cases = self.cases()
        cases.append(dict(cases[0]))
        self.save_cases(cases)
        self.assertRejected(
            "manifests/yaml/cases.jsonl:104: duplicate case id %s (also manifests/yaml/cases.jsonl:1)" % cases[0]["id"]
        )


class TestSecondShard(LayoutRepo):
    """A second implemented format, patched in for the test, to exercise cross-shard rules."""

    def add_testfmt(self, case_id):
        base = self.cases()[0]
        fixture = base["input"]["path"]
        case = json.loads(json.dumps(base))
        case.update(id=case_id, format="testfmt")
        case["expectations"] = {"events": base["expectations"]["events"]}
        case["input"]["path"] = fixture.replace("fixtures/yaml/", "fixtures/testfmt/")
        self.write(case["input"]["path"], self.read(fixture))
        self.save_cases([case], rel="manifests/testfmt/cases.jsonl", aggregate=False)
        doc = self.registry()
        doc["formats"] = {
            "yaml": doc["formats"]["yaml"],
            "testfmt": {
                "status": "active",
                "dialects": ["yaml-1.2.2"],
                "cases": "manifests/testfmt/cases.jsonl",
                "fixtures": "fixtures/testfmt",
            },
        }
        self.save_registry(doc)
        return case

    def test_aggregate_orders_by_sorted_format_id(self):
        with mock.patch.dict(corpus.IMPLEMENTED_FORMATS, {"testfmt": TESTFMT}):
            self.add_testfmt("testfmt.only")
            self.assertEqual(corpus.write_aggregate(self.root), ([], 104, True))
            self.assertEqual(
                self.read(corpus.AGGREGATE_REL), self.read("manifests/testfmt/cases.jsonl") + self.read(SHARD)
            )
            self.assertEqual(self.errors(), [])
            # Order comes from the format ids, never from JSON object or dict insertion order.
            formats = corpus.load_formats(self.root, [])
            reordered = {"yaml": formats["yaml"], "testfmt": formats["testfmt"]}
            self.assertEqual(corpus.build_aggregate(self.root, reordered, []), self.read(corpus.AGGREGATE_REL))

    def test_duplicate_id_across_shards(self):
        with mock.patch.dict(corpus.IMPLEMENTED_FORMATS, {"testfmt": TESTFMT}):
            dup = self.cases()[3]["id"]
            self.add_testfmt(dup)
            corpus.write_aggregate(self.root)
            self.assertRejected(
                "manifests/yaml/cases.jsonl:4: duplicate case id %s (also manifests/testfmt/cases.jsonl:1)" % dup
            )

    def test_record_format_must_match_its_shard(self):
        cases = self.cases()
        cases[2]["format"] = "json"
        self.save_cases(cases)
        self.assertRejected(
            "manifests/yaml/cases.jsonl:3 (%s): format 'json' does not match its shard's format 'yaml'" % cases[2]["id"]
        )

    def test_recipe_format_must_match_its_directory(self):
        rel = sorted(corpus.load_recipes(self.root, []))[0]
        doc = json.loads(self.read(rel))
        doc["format"] = "json"
        self.write(rel, json.dumps(doc))
        self.assertRejected("%s: format 'json' does not match its recipe directory's format 'yaml'" % rel)


class TestCaseNamespace(LayoutRepo):
    def smoke_recipe(self):
        recipes = corpus.load_recipes(self.root, [])
        return min(
            (rel for rel, d in recipes.items() if d["execution"]["tier"] == "smoke"),
            key=lambda rel: (recipes[rel]["expected"]["cases"], rel),
        ), recipes

    def test_static_id_inside_generated_namespace(self):
        rel, recipes = self.smoke_recipe()
        cases = self.cases()
        cases[0]["id"] = recipes[rel]["id"] + ".planted"
        self.save_cases(cases)
        self.assertRejected(
            "static case id %s is inside the generated case-id namespace of recipe %s (%s)"
            % (cases[0]["id"], recipes[rel]["id"], rel)
        )

    def test_hydrate_rejects_static_vs_generated_duplicate(self):
        rel, recipes = self.smoke_recipe()
        doc = recipes[rel]
        generated = next(corpus._recipe_cases(self.root, rel, doc))[0]
        cases = self.cases()
        cases[0]["id"] = generated
        self.save_cases(cases)
        with self.assertRaises(corpus.HydrateError) as ctx:
            corpus.hydrate(self.root, os.path.join(self.outdir, "h"), "smoke", {doc["id"]})
        self.assertIn("generated case id %s duplicates a static case" % generated, str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.outdir, "h")))

    def test_recipe_ids_sharing_a_generated_namespace(self):
        rel, recipes = self.smoke_recipe()
        doc = json.loads(self.read(rel))
        doc["id"] = doc["id"] + ".sub"
        self.write("recipes/yaml/%s.r%d.json" % (doc["id"], doc["revision"]), json.dumps(doc))
        self.assertRejected(
            "recipe ids %s and %s share a generated case-id namespace" % (recipes[rel]["id"], doc["id"])
        )

    def test_duplicate_recipe_id(self):
        rel, recipes = self.smoke_recipe()
        doc = json.loads(self.read(rel))
        doc["revision"] += 100
        other = "recipes/yaml/%s.r%d.json" % (doc["id"], doc["revision"])
        self.write(other, json.dumps(doc))
        first, second = sorted([rel, other])
        self.assertRejected("%s: recipe id %s is also declared by %s" % (second, doc["id"], first))


class TestUnregisteredPaths(LayoutRepo):
    def test_unregistered_format_directories(self):
        self.write("fixtures/json/a.json", b"{}\n")
        self.write("recipes/json/x.r1.json", b"{}\n")
        self.write("generators/json/gen.py", b"")
        errs = self.errors()
        for tree in ("fixtures", "recipes", "generators"):
            self.assertRejected(
                "%s/json: not a %s directory declared by an active format in manifests/formats.json" % (tree, tree),
                errs,
            )

    def test_unregistered_manifest_paths(self):
        self.write("manifests/json/cases.jsonl", b"")
        self.write("manifests/stray.json", b"{}\n")
        errs = self.errors()
        self.assertRejected("manifests/json: not a format directory declared by an active format", errs)
        self.assertRejected("manifests/stray.json: not a format directory declared by an active format", errs)

    def test_undeclared_path_inside_format_manifests(self):
        self.write("manifests/yaml/aliases.json", b"{}\n")
        self.assertRejected("manifests/yaml/aliases.json: not declared by manifests/formats.json for yaml")

    def test_unreferenced_generator(self):
        self.write("generators/yaml/orphan.py", b"def generate(parameters):\n    return []\n")
        self.assertRejected("generators/yaml/orphan.py: generator not referenced by any recipe")

    def test_non_recipe_file_in_recipe_directory(self):
        self.write("recipes/yaml/notes.txt", b"x\n")
        self.assertRejected("recipes/yaml/notes.txt: not a recipe record")

    def test_empty_declared_directory(self):
        top = self.full("manifests/yaml/span-conventions")
        for name in os.listdir(top):
            os.unlink(os.path.join(top, name))
        self.assertRejected("manifests/yaml/span-conventions: yaml declares span_conventions, but it is empty")


class TestRegistryContract(LayoutRepo):
    def test_unknown_member_in_entry(self):
        self.edit_yaml_entry(lambda e: e.update(aliases="manifests/yaml/aliases"))
        self.assertRejected("manifests/formats.json: yaml: unknown member(s) aliases")

    def test_unknown_top_level_member(self):
        doc = self.registry()
        doc["reserved"] = ["json"]
        self.save_registry(doc)
        self.assertRejected("manifests/formats.json: unknown member(s) reserved")

    def test_unknown_layout_version(self):
        doc = self.registry()
        doc["schema_version"] = "formats/v2"
        self.save_registry(doc)
        self.assertRejected("manifests/formats.json: unsupported schema_version 'formats/v2'")
        errors = []
        self.assertEqual(corpus.load_formats(self.root, errors), {})

    def test_duplicate_json_key(self):
        text = self.read(corpus.FORMATS_REL).replace(b'"status": "active",', b'"status": "active", "status": "active",')
        self.write(corpus.FORMATS_REL, text)
        self.assertRejected("manifests/formats.json: duplicate JSON key: 'status'")

    def test_missing_registry(self):
        os.unlink(self.full(corpus.FORMATS_REL))
        errs = self.errors()
        self.assertRejected("manifests/formats.json: [Errno 2]", errs)
        self.assertRejected("manifests/yaml: not a format directory declared by an active format", errs)

    def test_status_is_closed(self):
        self.edit_yaml_entry(lambda e: e.update(status="reserved"))
        self.assertRejected("manifests/formats.json: yaml: status must be \"active\", not 'reserved'")

    def test_active_entry_for_unimplemented_format(self):
        self.write("manifests/json/cases.jsonl", self.read(SHARD).splitlines(True)[0])
        doc = self.registry()
        doc["formats"]["json"] = {"status": "active", "dialects": ["rfc8259"], "cases": "manifests/json/cases.jsonl"}
        self.save_registry(doc)
        errs = self.errors()
        self.assertRejected(
            "manifests/formats.json: json: format is not implemented by this tool; an active entry does not enable it",
            errs,
        )
        errors = []
        self.assertEqual(sorted(corpus.load_formats(self.root, errors)), ["yaml"])
        built = corpus.build_aggregate(self.root, corpus.load_formats(self.root, []), [])
        self.assertEqual(built, self.read(SHARD))  # the unimplemented shard is never aggregated

    def test_unimplemented_dialect(self):
        self.edit_yaml_entry(lambda e: e.update(dialects=["yaml-1.2.2", "yaml-1.1"]))
        self.assertRejected("manifests/formats.json: yaml: dialect 'yaml-1.1' is not implemented for yaml")

    def test_generated_input_extension_is_the_implemented_one(self):
        self.edit_yaml_entry(lambda e: e.update(generated_input_extension=".yml"))
        self.assertRejected("manifests/formats.json: yaml: generated_input_extension must be '.yaml' for yaml")

    def test_recipes_need_an_extension(self):
        self.edit_yaml_entry(lambda e: e.pop("generated_input_extension"))
        self.assertRejected(
            "manifests/formats.json: yaml: generated_input_extension is declared exactly when recipes are"
        )

    def test_implemented_format_must_declare_its_inventories(self):
        self.edit_yaml_entry(lambda e: e.pop("upstreams"))
        errs = self.errors()
        self.assertRejected("manifests/formats.json: yaml: must declare upstreams", errs)
        # An entry with any problem is unusable, so none of its directories count as declared.
        self.assertRejected("manifests/yaml: not a format directory declared by an active format", errs)

    def test_missing_declared_path(self):
        os.unlink(self.full("manifests/yaml/upstreams.lock.json"))
        self.assertRejected(
            "manifests/formats.json: yaml.upstreams: manifests/yaml/upstreams.lock.json is missing (expected a file)"
        )


class TestRegistryPaths(LayoutRepo):
    def test_traversal_and_absolute_paths(self):
        for bad in ("manifests/yaml/../../outside/cases.jsonl", "/etc/cases.jsonl", "manifests//yaml/cases.jsonl"):
            with self.subTest(path=bad):
                self.edit_yaml_entry(lambda e, bad=bad: e.update(cases=bad))
                self.assertRejected("yaml.cases: %r is not a normalized repository-relative path" % bad)

    def test_root_aggregate_cannot_be_a_shard(self):
        self.edit_yaml_entry(lambda e: e.update(cases="manifests/cases.jsonl"))
        self.assertRejected("yaml.cases: manifests/cases.jsonl is the root aggregate and cannot also be a format shard")

    def test_unexpected_location(self):
        self.edit_yaml_entry(lambda e: e.update(fixtures="recipes/yaml"))
        self.assertRejected("yaml.fixtures: must be fixtures/yaml, not recipes/yaml")

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "symlinks unavailable")
    def test_symlinked_registry_directory(self):
        outside = os.path.join(self._tmp.name, "profiles-elsewhere")
        shutil.move(self.full("manifests/yaml/profiles"), outside)
        os.symlink(outside, self.full("manifests/yaml/profiles"))
        self.assertRejected("yaml.profiles: manifests/yaml/profiles is a symbolic link")

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "symlinks unavailable")
    def test_symlinked_parent_directory(self):
        outside = os.path.join(self._tmp.name, "yaml-elsewhere")
        shutil.move(self.full("manifests/yaml"), outside)
        os.symlink(outside, self.full("manifests/yaml"))
        errs = self.errors()
        self.assertRejected("yaml.cases: manifests/yaml is a symbolic link", errs)
        self.assertRejected("manifests/yaml: not a format directory declared by an active format", errs)

    def test_overlap_within_a_format(self):
        self.edit_yaml_entry(lambda e: e.update(span_conventions="manifests/yaml/profiles"))
        self.assertRejected(
            "manifests/formats.json: yaml.profiles (manifests/yaml/profiles) overlaps "
            "yaml.span_conventions (manifests/yaml/profiles)"
        )

    def test_overlap_across_formats(self):
        with mock.patch.dict(corpus.IMPLEMENTED_FORMATS, {"testfmt": TESTFMT}):
            doc = self.registry()
            doc["formats"]["testfmt"] = {
                "status": "active",
                "dialects": ["yaml-1.2.2"],
                "cases": "manifests/yaml/cases.jsonl",
                "fixtures": "fixtures/yaml",
            }
            self.save_registry(doc)
            errs = self.errors()
            self.assertRejected(
                "manifests/formats.json: testfmt.cases (manifests/yaml/cases.jsonl) overlaps "
                "yaml.cases (manifests/yaml/cases.jsonl)",
                errs,
            )
            self.assertRejected(
                "manifests/formats.json: testfmt.fixtures (fixtures/yaml) overlaps yaml.fixtures (fixtures/yaml)", errs
            )
            self.assertEqual(corpus.load_formats(self.root, []), {})


class TestHydratedPaths(LayoutRepo):
    def test_verify_rejects_unregistered_format(self):
        rel = min(r for r, d in corpus.load_recipes(self.root, []).items() if d["execution"]["tier"] == "smoke")
        doc = json.loads(self.read(rel))
        out = os.path.join(self.outdir, "h")
        corpus.hydrate(self.root, out, "smoke", {doc["id"]})
        self.assertEqual(corpus.verify(self.root, out), [])
        path = os.path.join(out, "cases.jsonl")
        with open(path, "rb") as fh:
            lines = fh.read().split(b"\n")
        rec = corpus.load_json_strict(lines[0])
        rec["format"] = "json"
        lines[0] = corpus.canonical_json(rec).encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(b"\n".join(lines))
        self.assertIn(
            "%s: format 'json' is not its recipe's registered format" % rec["id"], corpus.verify(self.root, out)
        )

    def test_generated_input_path_uses_registry_suffix(self):
        formats = {"yaml": {"generated_input_extension": ".yaml"}}
        rec = {"id": "core-truth-numbers.r0001", "format": "yaml"}
        self.assertEqual(corpus.generated_input_rel(formats, rec), "inputs/yaml/core-truth-numbers/r0001.yaml")


if __name__ == "__main__":
    unittest.main()
