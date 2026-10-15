"""Hand-checked rows for the adversarial-family generators (Python 3.9+ stdlib).

Each test states its expected value directly, from the cited specification
section, and checks the generator against it. The digests in the recipes only
show that output has not changed; these rows are what show it is right.
"""

import json
import math
import os
import struct
import sys
import unittest
from fractions import Fraction

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "generators", "yaml"))
sys.path.insert(0, os.path.join(REPO, "tools"))

import corpus  # noqa: E402
import escapes  # noqa: E402
import float_thresholds as ft  # noqa: E402
import merge_pairs  # noqa: E402
import tag_trees  # noqa: E402


def recipe(name):
    with open(os.path.join(REPO, "recipes", "yaml", name)) as fh:
        return json.load(fh)


def rows(module, name):
    return list(module.generate(recipe(name)["parameters"]))


def k_value(expectation):
    return expectation["documents"][0]["entries"][0][1]


class TestFloatThresholds(unittest.TestCase):
    def setUp(self):
        self.rows = rows(ft, "float-thresholds.r1.json")
        self.by_text = {r[2][3:-1]: r for r in self.rows}

    def bits(self, text):
        exp = self.by_text[text][3]
        return exp.get("error") or k_value(exp)["bits"]

    def typed(self, text, target):
        entry = next(t for t in self.by_text[text][4] if t["target"] == target)
        return entry.get("error") or entry["result"]["bits"]

    def test_rounder_known_values(self):
        self.assertEqual(ft.F64.bits(ft.F64.round(Fraction(1))), "3ff0000000000000")
        self.assertEqual(ft.F64.bits(ft.F64.round(Fraction(1, 10))), "3fb999999999999a")
        self.assertEqual(ft.F64.bits(ft.F64.round(ft.TWO**-1074)), "0000000000000001")
        self.assertEqual(ft.F32.bits(ft.F32.round(ft.F32_MAX)), "7f7fffff")
        self.assertIsNone(ft.F64.round(ft.F64_MAX + ft.TWO**970))

    def test_ties_to_even(self):
        # 1 + 2^-53 is halfway between 1 and 1 + 2^-52: ties to the even 1.
        self.assertEqual(self.bits("1.00000000000000011102230246251565404236316680908203125"), "3ff0000000000000")
        # 1 + 3 * 2^-53 is halfway between odd 1 + 2^-52 and even 1 + 2^-51: ties up.
        self.assertEqual(self.bits("1.00000000000000033306690738754696212708950042724609375"), "3ff0000000000002")

    def test_overflow_threshold(self):
        # The binary64 midpoint above DBL_MAX, 2^1024 - 2^970, ties to even: infinity, so an error.
        mid = decimal_of(ft.TWO**1024 - ft.TWO**970)
        self.assertEqual(self.bits(mid), {"phase": "resolution", "kind": "float_out_of_range"})
        self.assertEqual(self.bits("-" + mid), {"phase": "resolution", "kind": "float_out_of_range"})

    def test_smallest_subnormal_midpoint_ties_to_zero(self):
        mid = decimal_of(ft.TWO**-1075)
        self.assertEqual(self.bits(mid), "0000000000000000")
        self.assertEqual(self.bits("-" + mid), "8000000000000000")
        # f32 of -0.0 keeps the sign.
        self.assertEqual(self.typed("-" + mid, "f32"), "80000000")

    def test_f32_double_rounding(self):
        # Above the binary32 midpoint 1 + 2^-24, but within half a binary64 step of it:
        # binary64 rounds to the midpoint, and f32 then ties to even (1.0), not up.
        mid = 1 + ft.TWO**-24
        above = [
            t
            for t in self.by_text
            if not t.startswith(("-", "+", "0")) and "E" not in t and mid < Fraction(t) < mid + ft.TWO**-53
        ]
        self.assertEqual(len(above), 1)
        self.assertEqual(self.bits(above[0]), "3ff0000010000000")
        self.assertEqual(self.typed(above[0], "f32"), "3f800000")

    def test_f32_overflow_threshold_matches_spec_text(self):
        # Section 8: 2^128 - 2^103 rounds to infinity and is rejected.
        mid = decimal_of(ft.TWO**128 - ft.TWO**103)
        self.assertEqual(self.typed(mid, "f32"), {"phase": "typed", "kind": "float_out_of_range"})

    def test_rows_agree_with_host_conversion(self):
        # An observer, not the oracle: CPython's float() and struct are correctly rounded.
        for _lid, _cat, text, exp, typed in self.rows:
            x = float(text[3:-1])
            if math.isinf(x):
                self.assertIn("error", exp, text)
                continue
            self.assertEqual(k_value(exp)["bits"], struct.pack(">d", x).hex(), text)
            f32 = next(t for t in typed if t["target"] == "f32")
            try:
                host = struct.pack(">f", x).hex()
            except OverflowError:
                host = None
            self.assertEqual(f32.get("result", {}).get("bits"), host, text)

    def test_both_signs_and_spellings(self):
        texts = [r[2] for r in self.rows]
        self.assertEqual(len(texts), len(set(texts)))
        positives = [t for t in texts if not t.startswith("k: -")]
        self.assertEqual(sum(1 for t in texts if t.startswith("k: -")), len(ft.rows()))
        self.assertTrue(any("E" in t for t in positives) and any(t.startswith("k: +") for t in positives))


def decimal_of(q):
    return ft.decimal_text(q)


class TestEscapes(unittest.TestCase):
    def setUp(self):
        self.rows = {r[0]: r for r in rows(escapes, "escapes.r1.json")}

    def value(self, lid):
        return k_value(self.rows[lid][3])["v"]

    def test_each_escape_by_hand(self):
        by_text = {r[2]: r for r in self.rows.values()}
        hand = {
            'k: "\\0"\n': "\x00",
            'k: "\\e"\n': "\x1b",
            'k: "\\N"\n': "\x85",
            'k: "\\_"\n': "\xa0",
            'k: "\\L"\n': "\u2028",
            'k: "\\xe9"\n': "é",
            'k: "\\U0001F600"\n': "\U0001f600",
            'k: "\\/"\n': "/",
        }
        for text, want in hand.items():
            self.assertEqual(k_value(by_text[text][3])["v"], want, text)

    def test_escaped_line_breaks(self):
        self.assertEqual(self.value("lb1"), "ab")
        self.assertEqual(self.value("lb2"), "a b")
        self.assertEqual(self.value("lb3"), "a  b")

    def test_ladder_lengths_differ(self):
        for size in escapes.SIZES:
            _lid, _cat, text, exp, _ = self.rows["l%05d" % size]
            encoded = text[len('k: "') : -2]
            self.assertGreaterEqual(len(encoded), size)
            self.assertNotEqual(len(k_value(exp)["v"].encode()), len(encoded.encode()))

    def test_malformed_are_syntax(self):
        bad = [r for lid, r in self.rows.items() if lid.startswith("t")]
        self.assertTrue(any(r[2] == 'k: "\\U0010FFF"\n' for r in bad))
        self.assertTrue(any(r[2] == 'k: "\\q"\n' for r in bad))
        for r in bad:
            self.assertEqual(r[3], {"error": {"phase": "syntax"}}, r[2])


class TestMergePairs(unittest.TestCase):
    def test_reproduces_goldens(self):
        # The order rules of section 5.3, as in the hand goldens g105, g107, g108.
        self.assertEqual(merge_pairs.merge([("y", "2")], 1, [[("x", "1"), ("y", "1")]]), [("y", "2"), ("x", "1")])
        self.assertEqual(merge_pairs.merge([("y", "2")], 0, [[("x", "1"), ("y", "1")]]), [("x", "1"), ("y", "2")])
        self.assertEqual(merge_pairs.merge([], 0, [[("x", "1")], [("x", "2"), ("z", "2")]]), [("x", "1"), ("z", "2")])

    def test_pairs_share_expectations_and_differ_in_text(self):
        out = rows(merge_pairs, "merge-pairs.r1.json")
        self.assertEqual(len(out) % 2, 0)
        for alias, inline in zip(out[::2], out[1::2]):
            self.assertEqual(alias[0].replace("-alias", ""), inline[0].replace("-inline", ""))
            self.assertEqual(alias[3], inline[3])
            self.assertIn("*p", alias[2])
            self.assertNotIn("*", inline[2])

    def test_smallest_seq_by_hand(self):
        alias, inline, exp = merge_pairs.case(1, "seq")
        self.assertEqual(alias, "p: &p {k0000: 0}\nq: &q {k0000: q0}\nm: {k0000: own, <<: [*p, *q], z: last}\n")
        m = exp["documents"][0]["entries"][2][1]
        # The explicit key shadows both sources, so nothing is merged in.
        self.assertEqual([e[0]["v"] for e in m["entries"]], ["k0000", "z"])


class TestTagTrees(unittest.TestCase):
    def test_weight_by_hand(self):
        # "!t x": wrapper 64 + uri "!t" 2 + handle "!" 1 + suffix "t" 1, inner 64 + 1.
        self.assertEqual(tag_trees.weight(tag_trees.T("t", tag_trees.S("x"))), 64 + 4 + 65)
        self.assertEqual(tag_trees.nodes(tag_trees.T("t", tag_trees.S("x"))), 2)
        # A mapping charges 24 per entry on top of its keys and values.
        m = tag_trees.MAP([(tag_trees.S("a"), tag_trees.S(""))])
        self.assertEqual(tag_trees.weight(m), 64 + 24 + 65 + 64)

    def test_weight_worked_examples(self):
        # Worked numbers written out for section 6: [~, ~] is 192 and {a: b} is 218.
        null = {"t": "null"}
        self.assertEqual(tag_trees.weight(tag_trees.SEQ([null, null])), 192)
        self.assertEqual(tag_trees.weight(tag_trees.MAP([(tag_trees.S("a"), tag_trees.S("b"))])), 218)

    def test_limits_rows_bracket_profile(self):
        doc = recipe("tag-trees-limits.r1.json")
        with open(os.path.join(REPO, "manifests", "profiles", "yamlprims-core-limits.r1.json")) as fh:
            limits = json.load(fh)["limits"]
        self.assertEqual(doc["parameters"]["max_nodes"], limits["max_nodes"])
        self.assertEqual(doc["parameters"]["max_owned_bytes"], limits["max_owned_bytes"])
        out = rows(tag_trees, "tag-trees-limits.r1.json")
        self.assertEqual(
            [r[3].get("error", {}).get("limit") for r in out],
            [None, None, "max_nodes"] + [None, None, "max_owned_bytes"],
        )
        for _lid, _cat, text, exp, _ in out:
            # No other limit can be the one that fails.
            self.assertLessEqual(len(text.encode()), limits["max_input_bytes"])
            if "documents" in exp:
                root = exp["documents"][0]
                self.assertLessEqual(tag_trees.nodes(root), limits["max_nodes"])
                self.assertLessEqual(tag_trees.weight(root), limits["max_owned_bytes"])
                for item in root["items"]:
                    inner = item["inner"] if item["t"] == "tagged" else item
                    self.assertLessEqual(len(inner["v"].encode()), limits["max_scalar_bytes"])

    def test_values_by_hand(self):
        out = {r[0]: r for r in rows(tag_trees, "tag-trees.r1.json")}
        self.assertEqual(
            out["core-beside"][3]["documents"][0]["items"][3], {"t": "str", "v": "7"}
        )  # the non-specific tag gives a String (4.4)
        self.assertEqual(out["keys-equal"][3], {"error": {"phase": "structure", "kind": "duplicate_key"}})
        self.assertEqual(len(out["seq10000"][3]["documents"][0]["items"]), 10000)


class TestRecipesAreSmall(unittest.TestCase):
    def test_new_recipes_are_smoke_and_capped(self):
        for name in (
            "float-thresholds.r1.json",
            "escapes.r1.json",
            "merge-pairs.r1.json",
            "tag-trees.r1.json",
            "tag-trees-limits.r1.json",
        ):
            doc = recipe(name)
            self.assertEqual(doc["execution"]["tier"], "smoke", name)
            self.assertEqual(doc["review"]["status"], "provisional", name)
            self.assertLessEqual(doc["expected"]["input_bytes"], 256 * 1024, name)
            self.assertIn(doc["profile"], ("yamlprims-core", "yamlprims-core-merge-apply", "yamlprims-core-limits"))
            corpus.canonical_json(doc)


if __name__ == "__main__":
    unittest.main()
