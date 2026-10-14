"""Generator self-consistency tests (Python 3.9+ stdlib)."""

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


if __name__ == "__main__":
    unittest.main()
