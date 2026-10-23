"""Generator self-consistency tests (Python 3.9+ stdlib)."""

import json
import os
import struct
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "generators", "yaml"))
sys.path.insert(0, os.path.join(REPO, "tools"))

import core_goldens  # noqa: E402
import core_truth  # noqa: E402
import corpus  # noqa: E402
import spec14_boundaries  # noqa: E402


def value(target, text, plain=True, tag=None):
    return core_truth.typed_scalar(core_truth.resolve(text, plain, tag), target)


class TestGoldens(unittest.TestCase):
    def test_ids_unique_and_portable(self):
        ids = [r[0] for r in core_goldens.ROWS]
        self.assertEqual(len(ids), len(set(ids)))
        for i in ids:
            self.assertRegex(i, r"^g[0-9]{3}$")

    def test_every_row_in_exactly_one_policy(self):
        total = sum(sum(1 for _ in core_goldens.generate({"merge_policy": p})) for p in core_goldens.PROFILES)
        self.assertEqual(total, len(core_goldens.ROWS))

    def test_rows_are_metadata_subset(self):
        for lid, _cat, _pol, _text, exp, typed in core_goldens.ROWS:
            corpus.canonical_json(exp)
            for t in typed:
                corpus.canonical_json(t)
                self.assertIn(t["target"], corpus.TYPED_TARGETS)
                self.assertEqual(("result" in t) + ("error" in t), 1, lid)

    def test_merge_rows_only_under_merge_profiles(self):
        for lid, cat, pol, _text, _exp, _typed in core_goldens.ROWS:
            if pol != "reject":
                self.assertEqual(cat, "merge-policy", lid)


class TestTypedConversion(unittest.TestCase):
    """Boundary rows for spec section 8, written out independently of the tables."""

    def test_integer_widths(self):
        self.assertEqual(value("u8", "255"), ("result", {"t": "int", "v": "255"}))
        self.assertEqual(value("u8", "256"), ("error", {"phase": "typed", "kind": "integer_out_of_range"}))
        self.assertEqual(value("i8", "-128"), ("result", {"t": "int", "v": "-128"}))
        self.assertEqual(value("i8", "-129"), ("error", {"phase": "typed", "kind": "integer_out_of_range"}))
        self.assertEqual(value("u64", "-1"), ("error", {"phase": "typed", "kind": "integer_out_of_range"}))

    def test_no_coercion(self):
        for target in ("u16", "i64", "f64", "bool"):
            self.assertEqual(value(target, "8080", plain=False)[0], "error", target)
        self.assertEqual(value("u16", "1.0"), ("error", {"phase": "typed", "kind": "type"}))
        self.assertEqual(value("string", "1"), ("error", {"phase": "typed", "kind": "type"}))

    def test_int_to_float_exactness(self):
        self.assertEqual(value("f64", "9007199254740992"), ("result", core_truth.FLT(2.0**53)))
        self.assertEqual(value("f64", "9007199254740993")[0], "error")
        self.assertEqual(value("f32", "16777216"), ("result", {"t": "float32", "bits": "4b800000"}))
        self.assertEqual(value("f32", "16777217")[0], "error")

    def test_f32_threshold(self):
        # 2^128 - 2^103 ties to even and overflows; the value just below rounds to f32::MAX.
        self.assertEqual(value("f32", "3.4028235677973362e38"), ("result", {"t": "float32", "bits": "7f7fffff"}))
        self.assertEqual(
            value("f32", "3.4028235677973366e38"), ("error", {"phase": "typed", "kind": "float_out_of_range"})
        )
        self.assertEqual(
            value("f32", "-3.4028235677973366e38"), ("error", {"phase": "typed", "kind": "float_out_of_range"})
        )
        self.assertEqual(value("f32", "3.4028235e38"), ("result", {"t": "float32", "bits": "7f7fffff"}))

    def test_f32_specials(self):
        self.assertEqual(value("f32", ".nan"), ("result", {"t": "float32", "bits": "7fc00000"}))
        self.assertEqual(value("f32", "-.inf"), ("result", {"t": "float32", "bits": "ff800000"}))
        self.assertEqual(value("f32", "-0.0"), ("result", {"t": "float32", "bits": "80000000"}))

    def test_option_bool(self):
        self.assertEqual(value("option-bool", "~"), ("result", {"t": "none"}))
        self.assertEqual(value("option-bool", "true"), ("result", {"t": "bool", "v": True}))
        self.assertEqual(value("option-bool", "yes"), ("error", {"phase": "typed", "kind": "type"}))

    def test_generic_failure_carries_over(self):
        failure = {"phase": "resolution", "kind": "integer_out_of_range"}
        [entry] = core_truth.typed_entries(["k"], ["u8"], failure=failure)
        self.assertEqual(entry, {"path": ["k"], "target": "u8", "error": failure})

    def test_tagged_values_do_not_convert(self):
        rows = [r for r in core_truth.gen_booleans(typed=True) if r[1] == "scalar-resolution"]
        tagged = [r for r in rows if "!custom" in r[2] and r[2].startswith("k: ")]
        self.assertTrue(tagged)
        for rid, _cat, _y, _exp, typed in tagged:
            self.assertEqual({t["error"]["kind"] for t in typed}, {"type"}, rid)

    def test_typed_only_at_block_value(self):
        for rid, _cat, y, _exp, typed in core_truth.gen_booleans(typed=True):
            if typed:
                self.assertTrue(y.startswith("k: ") or y.startswith("k: |") or y.startswith("k: >"), rid)

    def test_struct_matches_round_to_nearest_even(self):
        # Halfway between 1.0 and the next binary32 value rounds to even (1.0).
        half = 1.0 + 2.0**-24
        self.assertEqual(struct.pack(">f", half).hex(), "3f800000")


class TestSpec14Boundaries(unittest.TestCase):
    """Section 6 and section 5.2 rows, checked against the published arithmetic."""

    def test_limit_fields_match_the_corpus_tool(self):
        self.assertEqual(spec14_boundaries.LIMIT_FIELDS, corpus.LIMIT_FIELDS)

    def test_spec_table_levels_and_weights(self):
        self.assertEqual(spec14_boundaries.alias_levels(125), (126, 127))
        self.assertEqual(spec14_boundaries.alias_levels(126), (127, 128))
        self.assertEqual(spec14_boundaries.alias_levels(127), (128, 129))
        text, value = spec14_boundaries.seq_text(128)
        self.assertEqual(text, ("[" * 128) + "0" + ("]" * 128) + "\n")
        self.assertEqual(spec14_boundaries.node_count(value), 129)
        self.assertEqual(spec14_boundaries.logical_weight(value), 64 * 129)
        text, value = spec14_boundaries.alias_text(126)
        self.assertTrue(text.startswith("{a: &a [], b: "))
        self.assertTrue(text.endswith("*a" + ("]" * 126) + "}\n"))
        # 64 map + 48 entry charges + two 65-byte keys + 64-byte anchor
        # + 64 bytes for each of k nested sequences and the copy.
        self.assertEqual(spec14_boundaries.logical_weight(value), 306 + 64 * 127)
        self.assertEqual(spec14_boundaries.node_count(value), 131)

    def _params(self, profile_name, kind):
        with open(os.path.join(REPO, "manifests", "profiles", profile_name)) as fh:
            limits = json.load(fh)["limits"]
        params = {"set": kind}
        params.update({("limit_" + name): value for name, value in limits.items()})
        return params

    def test_depth_and_entry_outcomes(self):
        depth = {
            row[0]: row for row in spec14_boundaries.generate(self._params("yamlprims-core-depth128.r1.json", "depth"))
        }
        self.assertIn("documents", depth["depth-127"][3])
        self.assertIn("documents", depth["depth-128"][3])
        self.assertEqual(depth["depth-129"][3]["error"]["configured"], 128)
        self.assertNotIn("error", depth["alias-126"][3])
        self.assertIn("documents", depth["alias-126"][3])
        self.assertEqual(depth["alias-127"][3]["error"]["limit"], "max_depth")
        generated = spec14_boundaries.generate(self._params("yamlprims-core-entries2.r1.json", "entries"))
        entries = {row[0]: row for row in generated}
        self.assertIn("documents", entries["entries-two"][3])
        self.assertEqual(entries["entries-duplicate"][3]["error"], {"phase": "structure", "kind": "duplicate_key"})
        for name in ("entries-third-duplicate", "entries-third-new"):
            self.assertEqual(
                entries[name][3]["error"],
                {"phase": "limit", "kind": "limit_exceeded", "limit": "max_mapping_entries", "configured": 2},
                name,
            )

    def test_recorded_recipe_digests(self):
        errors = []
        recipes = corpus.load_recipes(REPO, errors)
        self.assertEqual(errors, [])
        for rel in ("recipes/yaml/depth-boundaries.r1.json", "recipes/yaml/entry-admission.r1.json"):
            doc = recipes[rel]
            lines = []
            in_bytes = 0
            for _cid, data, _rec, line in corpus._recipe_cases(REPO, rel, doc):
                lines.append(line)
                in_bytes += len(data)
            self.assertEqual(doc["expected"]["cases"], len(lines), rel)
            self.assertEqual(doc["expected"]["input_bytes"], in_bytes, rel)
            self.assertEqual(doc["expected"]["digest"], corpus.recipe_digest(lines), rel)

    def test_new_profiles_are_bound_only_by_the_new_recipes(self):
        errors = []
        recipes = corpus.load_recipes(REPO, errors)
        self.assertEqual(errors, [])
        bound = {}
        for doc in recipes.values():
            bound.setdefault((doc["profile"], doc["profile_revision"]), set()).add(doc["id"])
        self.assertEqual(bound[("yamlprims-core-depth128", 1)], {"depth-boundaries"})
        self.assertEqual(bound[("yamlprims-core-entries2", 1)], {"entry-admission"})
        for key in (
            ("yamlprims-core", 4),
            ("yamlprims-core-stream", 4),
            ("yamlprims-core-merge-apply", 4),
            ("yamlprims-core-merge-as-key", 4),
        ):
            self.assertNotIn(key, bound)


if __name__ == "__main__":
    unittest.main()
