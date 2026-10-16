"""Case-record validation and canonical JSON tests (Python 3.9+ stdlib)."""

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


class TestCanonicalJson(unittest.TestCase):
    def test_rfc8785_sorting_vector(self):
        # RFC 8785 section 3.2.3: members sort by UTF-16 code units.
        value = {
            "€": "Euro Sign",
            "\r": "Carriage Return",
            "דּ": "Hebrew Letter Dalet With Dagesh",
            "1": "One",
            "\U0001f600": "Emoji: Grinning Face",
            "\u0080": "Control",
            "ö": "Latin Small Letter O With Diaeresis",
        }
        out = corpus.canonical_json(value)
        order = list(json.loads(out, object_pairs_hook=lambda p: [k for k, _ in p]))
        self.assertEqual(order, ["\r", "1", "\u0080", "ö", "€", "\U0001f600", "דּ"])

    def test_utf16_differs_from_code_point_order(self):
        value = {"דּ": 1, "\U0001f600": 2}
        self.assertEqual(sorted(value), ["דּ", "\U0001f600"])  # code-point order
        self.assertTrue(corpus.canonical_json(value).startswith('{"\U0001f600"'))

    def test_string_escaping(self):
        # RFC 8785 section 3.2.2.2: short escapes, \\u00XX for other controls, rest literal.
        s = '\u0000\u0008\u0009\u000a\u000c\u000d\u001f"\\/\u007f€'
        self.assertEqual(corpus.canonical_json(s), '"\\u0000\\b\\t\\n\\f\\r\\u001f\\"\\\\/\u007f€"')

    def test_structure_and_whitespace(self):
        self.assertEqual(corpus.canonical_json({"b": [1, True, None], "a": {}}), '{"a":{},"b":[1,true,null]}')

    def test_rejects_outside_subset(self):
        for value in (1.5, 2**53, "\ud800", {"k": float("nan")}):
            with self.assertRaises(ValueError):
                corpus.canonical_json(value)

    def test_round_trip_is_stable(self):
        text = corpus.canonical_json({"z": "é", "a": [{"y": 1, "x": 2}]})
        self.assertEqual(corpus.canonical_json(corpus.load_json_strict(text.encode())), text)


class CaseRepo(unittest.TestCase):
    """A disposable copy of the repository's manifests and fixtures."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        for sub in ("manifests", "fixtures"):
            shutil.copytree(os.path.join(REPO, sub), os.path.join(self.root, sub))
        shutil.copy(os.path.join(REPO, ".gitattributes"), self.root)
        with open(os.path.join(self.root, "manifests", "cases.jsonl"), "rb") as fh:
            self.cases = [json.loads(line) for line in fh.read().splitlines() if line.strip()]
        self.base = [json.loads(json.dumps(c)) for c in self.cases]

    def tearDown(self):
        self._tmp.cleanup()

    def save(self, cases=None, raw=None):
        with open(os.path.join(self.root, "manifests", "cases.jsonl"), "wb") as fh:
            if raw is not None:
                fh.write(raw)
            else:
                for c in cases if cases is not None else self.cases:
                    fh.write(json.dumps(c, ensure_ascii=False).encode() + b"\n")

    def errors(self):
        return corpus.check_repository(self.root) + corpus.check_manifests(self.root)

    def assertRejected(self, needle):
        errs = self.errors()
        self.assertTrue(any(needle in e for e in errs), "expected %r in %r" % (needle, errs))

    def mutate(self, index, fn):
        fn(self.cases[index])
        self.save()


SPEC_V11_URL = "https://github.com/3leaps/yamlprims/blob/spec-v1.1/docs/spec/yamlprims-spec.md"


class TestShippedCases(CaseRepo):
    def test_shipped_manifests_are_valid(self):
        self.assertEqual(self.errors(), [])

    def test_shipped_cases_cover_every_layer(self):
        layers = set()
        for c in self.cases:
            layers.update(c["expectations"])
        self.assertEqual(layers, {"events", "value", "typed", "locations", "node_locations"})


class TestEventNotation(CaseRepo):
    """Expected events use the pinned yaml-test-suite notation exactly."""

    def case(self, cid):
        return next(c for c in self.cases if c["id"] == cid)

    def test_flow_sequence_control_exact_events(self):
        # A flow sequence starts with "+SEQ []" in the pinned notation, not a bare "+SEQ".
        self.assertEqual(
            self.case("yaml.syntax.flow-indented-control")["expectations"]["events"]["events"],
            [
                "+STR",
                "+DOC ---",
                "+MAP",
                "=VAL :flow",
                "+SEQ []",
                "=VAL :a",
                "=VAL :b",
                "=VAL :c",
                "-SEQ",
                "-MAP",
                "-DOC",
                "-STR",
            ],
        )

    def test_flow_markers_match_flow_openers(self):
        # For inputs without quotes or comments, every "[" or "{" opens a flow collection,
        # so the number of flow-marked start events must equal the number of openers.
        checked = 0
        for c in self.cases:
            ev = c["expectations"]["events"]
            if ev["status"] != "valid":
                continue
            with open(os.path.join(REPO, *c["input"]["path"].split("/")), "rb") as fh:
                data = fh.read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue  # a valid non-UTF-8 stream (for example UTF-16); counting bytes says nothing
            if any(ch in text for ch in "\"'#"):
                continue
            openers = text.count("[") + text.count("{")
            marked = sum(1 for e in ev["events"] if e.startswith(("+SEQ []", "+MAP {}")))
            self.assertEqual(marked, openers, c["id"])
            checked += 1
        self.assertGreater(checked, 10)

    def test_bin_extension_marks_non_text_inputs(self):
        # DDR-0001 section 3: inputs with invalid UTF-8 or NUL use .bin, and only those.
        for c in self.cases:
            path = c["input"]["path"]
            with open(os.path.join(REPO, *path.split("/")), "rb") as fh:
                data = fh.read()
            try:
                data.decode("utf-8")
                text = b"\x00" not in data
            except UnicodeDecodeError:
                text = False
            self.assertEqual(path.endswith(".bin"), not text, c["id"])

    def test_flow_marker_precedes_properties(self):
        # Upstream order is the style marker, then anchor and tag: "+SEQ [] &a".
        for c in self.cases:
            for e in c["expectations"]["events"].get("events", []):
                if e.startswith(("+SEQ ", "+MAP ")):
                    rest = e[5:]
                    if "[]" in rest or "{}" in rest:
                        self.assertTrue(rest.startswith(("[]", "{}")), (c["id"], e))


SPEC_V13_URL = "https://github.com/3leaps/yamlprims/blob/spec-v1.3/docs/spec/yamlprims-spec.md"


class TestSpec13(CaseRepo):
    """Exact rows from the yamlprims specification revision 1.3 tables, written out here."""

    # (input bytes, node path, span) from section 7.2: nine revision 1.2 rows, ten revision 1.3 rows.
    ANCHORS = [
        (b"k: |\n  \n  \nx: 1\n", [{"value": 0}], (10, 10)),
        (b"k: |\n\nx: 1\n", [{"value": 0}], (4, 4)),
        (b"k: |\n\n", [{"value": 0}], (3, 4)),
        (b"k: |\n", [{"value": 0}], (3, 4)),
        (b"k: >-\n\nx: 1\n", [{"value": 0}], (5, 5)),
        (b"k: |+\n\n\nx: 1\n", [{"value": 0}], (5, 5)),
        (b"k: |\r\n\r\nx: 1\r\n", [{"value": 0}], (4, 4)),
        (b"k: | # c\n\nx: 1\n", [{"value": 0}], (8, 8)),
        (b"- |\n\n- a\n", [{"item": 0}], (3, 3)),
        (b"\xef\xbb\xbfk: |\n\nx: 1\n", [{"value": 0}], (7, 7)),
        (b"k: |\r\rx: 1\r", [{"value": 0}], (4, 4)),
        (b"k: !t |\n\nx: 1\n", [{"value": 0}], (7, 7)),
        (b"k: !t |\n\nx: 1\n", [{"value": 0}, {"inner": True}], (7, 7)),
        (b"k: !!str |\n\nx: 1\n", [{"value": 0}], (10, 10)),
        (b"k: &a |\n\nx: 1\n", [{"value": 0}], (7, 7)),
        (b"a: 0\nk: |\n\nx: 1\n", [{"value": 1}], (9, 9)),
        (b"p:\n  ? a\n  ? b\n", [{"value": 0}, {"value": 0}], (8, 8)),
        (b"p:\n  k: |\n\n  x: 1\n", [{"value": 0}, {"value": 0}], (9, 9)),
        (b"?\n\n :\n", [{"key": 0}], (4, 4)),
        (b"?\n !m\n :\n", [{"key": 0}], (7, 7)),
        (b"?\n !m\n :\n", [{"key": 0}, {"inner": True}], (7, 7)),
    ]
    KEEP_EOF = {b"k: |+\n\n   ": "\n", b"k: |+\n\n   \n": "\n\n", b"k: |+\r\n\r\n   ": "\n"}

    def by_input(self):
        out = {}
        for c in self.cases:
            with open(os.path.join(REPO, *c["input"]["path"].split("/")), "rb") as fh:
                out.setdefault(fh.read(), []).append(c)
        return out

    def test_every_anchor_row_is_pinned_exactly(self):
        found = self.by_input()
        for data, path, (start, end) in self.ANCHORS:
            cases = [c for c in found.get(data, []) if "node_locations" in c["expectations"]]
            self.assertEqual(len(cases), 1, data)
            nl = cases[0]["expectations"]["node_locations"]
            self.assertEqual((nl["profile"], nl["profile_revision"]), ("yamlprims-core", 3), data)
            spans = [(s["start"], s["end"]) for s in nl["spans"] if s["path"] == path and s["document"] == 0]
            self.assertEqual(spans, [(start, end)], (data, path))

    def test_anchor_count_matches_spec(self):
        anchored = [c for c in self.cases if "node_locations" in c["expectations"]]
        self.assertEqual(len(anchored), 19)
        self.assertEqual(sum(len(c["expectations"]["node_locations"]["spans"]) for c in anchored), len(self.ANCHORS))

    def test_wrapper_and_inner_share_span(self):
        for c in self.cases:
            nl = c["expectations"].get("node_locations")
            if not nl:
                continue
            spans = {canonical(s["path"]): (s["start"], s["end"]) for s in nl["spans"]}
            for path, span in spans.items():
                inner = canonical(json.loads(path) + [{"inner": True}])
                if inner in spans:
                    self.assertEqual(spans[inner], span, c["id"])

    def test_keep_chomping_at_eof(self):
        found = self.by_input()
        for data, want in self.KEEP_EOF.items():
            [c] = found[data]
            [v] = c["expectations"]["value"]
            self.assertEqual((v["profile"], v["profile_revision"]), ("yamlprims-core", 3))
            self.assertEqual(v["documents"][0]["entries"][0][1], {"t": "str", "v": want}, data)

    def test_bom_only_utf32_is_valid_format_but_fails_input_gate(self):
        [c] = [c for c in self.cases if c["id"] == "yaml.input.utf32be-bom-only"]
        self.assertEqual(
            c["expectations"]["events"], {"notation": "yaml-test-suite", "status": "valid", "events": ["+STR", "-STR"]}
        )
        self.assertEqual([v["error"] for v in c["expectations"]["value"]], [{"phase": "input", "kind": "invalid_utf8"}])

    def test_escaped_nul_event_text_and_value(self):
        # The event text spells the escape (backslash, zero); the decoded value holds U+0000.
        [c] = [c for c in self.cases if c["id"] == "yaml.input.escaped-nul"]
        self.assertEqual(c["expectations"]["events"]["events"][4], '=VAL "a\\0b')
        [v] = c["expectations"]["value"]
        self.assertEqual(v["documents"][0]["entries"][0][1], {"t": "str", "v": "a\u0000b"})

    def test_nonzero_eof_anchors_are_in_convention_scope(self):
        with open(os.path.join(self.root, "manifests", "span-conventions", "yamlprims-node.r1.json")) as fh:
            conv = json.load(fh)
        self.assertNotIn("zero-width nodes only", conv["rules"]["scope"])
        self.assertIn("[3, 4)", conv["rules"]["non-zero-width-block-scalar"])

    def test_f32_example(self):
        [c] = [c for c in self.cases if c["id"] == "yaml.typed.f32-double-rounding"]
        typed = {t["target"]: t["result"] for t in c["expectations"]["typed"]}
        self.assertEqual(typed["f32"], {"t": "float32", "bits": "3f800000"})
        self.assertEqual(typed["f64"], {"t": "float", "bits": "3ff0000010000000"})

    def test_utf8_surface_examples(self):
        found = self.by_input()
        expect = {
            b"\x00\x00\xfe\xff": {"phase": "input", "kind": "invalid_utf8"},
            "k: v\n".encode("utf-16-le"): {"phase": "syntax"},
        }
        for data, err in expect.items():
            [c] = found[data]
            r3 = [v for v in c["expectations"]["value"] if v["profile_revision"] == 3]
            self.assertEqual([v["error"] for v in r3], [err], data)

    def test_r3_profiles_cite_spec_13(self):
        for name in os.listdir(os.path.join(self.root, "manifests", "profiles")):
            if name.endswith(".r3.json") or name == "yamlprims-core-limits.r2.json":
                with open(os.path.join(self.root, "manifests", "profiles", name)) as fh:
                    prof = json.load(fh)
                self.assertEqual(prof["cites"][0]["url"], SPEC_V13_URL, name)
                self.assertIn("4cf97b2d4efec16b6b41ea6e1acb83164a76aa45", prof["cites"][0]["revision"], name)

    def test_older_profiles_keep_their_binding(self):
        for name in os.listdir(os.path.join(self.root, "manifests", "profiles")):
            with open(os.path.join(self.root, "manifests", "profiles", name)) as fh:
                prof = json.load(fh)
            if prof["id"].startswith("yamlprims-core") and not (
                name.endswith(".r3.json") or name == "yamlprims-core-limits.r2.json"
            ):
                self.assertNotIn(SPEC_V13_URL, [c["url"] for c in prof["cites"]], name)


class TestLimitConfigured(CaseRepo):
    """configured on limit errors (DDR-0009), on the committed alias-event limit case."""

    def limit_case(self):
        return next(i for i, c in enumerate(self.cases) if c["id"] == "yaml.aliases.alias-events-limit")

    def set_error(self, **err):
        def edit(c):
            v = next(v for v in c["expectations"]["value"] if "error" in v)
            v["error"] = dict({"phase": "limit", "kind": "limit_exceeded", "limit": "max_alias_events"}, **err)

        self.mutate(self.limit_case(), edit)

    def test_matching_configured_is_accepted(self):
        self.set_error(configured=8)
        self.assertEqual([e for e in self.errors() if "configured" in e or "Limits field" in e], [])

    def test_wrong_configured(self):
        self.set_error(configured=9)
        self.assertRejected("configured 9 does not match the profile's max_alias_events = 8")

    def test_unknown_limit_name(self):
        self.set_error(limit="max_magic")
        self.assertRejected("is not a Limits field")

    def test_configured_outside_limit_phase(self):
        def edit(c):
            v = next(v for v in c["expectations"]["value"] if "error" in v)
            v["error"] = {"phase": "syntax", "configured": 8}

        self.mutate(self.limit_case(), edit)
        self.assertRejected("configured is only for limit errors")

    def test_configured_needs_explicit_limits(self):
        def edit(c):
            c["expectations"]["value"] = [
                {
                    "profile": "yamlprims-core",
                    "profile_revision": 3,
                    "error": {"phase": "limit", "kind": "limit_exceeded", "limit": "max_alias_events", "configured": 8},
                }
            ]

        self.mutate(self.limit_case(), edit)
        self.assertRejected("configured needs a profile with explicit limits")


class TestNodeLocationRejections(CaseRepo):
    def anchored(self, cid="yaml.anchors.tagged"):
        return next(i for i, c in enumerate(self.cases) if c["id"] == cid)

    def test_path_must_resolve(self):
        self.mutate(
            self.anchored(), lambda c: c["expectations"]["node_locations"]["spans"][0].update(path=[{"value": 5}])
        )
        self.assertRejected("does not resolve")

    def test_inner_needs_tagged(self):
        self.mutate(
            self.anchored("yaml.anchors.r12-blank-then-sibling"),
            lambda c: c["expectations"]["node_locations"]["spans"][0].update(path=[{"value": 0}, {"inner": True}]),
        )
        self.assertRejected("does not resolve")

    def test_inner_step_must_be_true(self):
        path = [{"value": 0}, {"inner": False}]
        self.mutate(self.anchored(), lambda c: c["expectations"]["node_locations"]["spans"][1].update(path=path))
        self.assertRejected("does not resolve")

    def test_key_step_needs_mapping(self):
        self.mutate(
            self.anchored("yaml.anchors.r12-seq-item"),
            lambda c: c["expectations"]["node_locations"]["spans"][0].update(path=[{"key": 0}]),
        )
        self.assertRejected("does not resolve")

    def with_event_char(self, ch):
        """A fresh copy of the cases where the escaped-NUL case's scalar event holds ch raw."""
        self.cases = [json.loads(json.dumps(c)) for c in self.base]
        idx = next(i for i, c in enumerate(self.cases) if c["id"] == "yaml.input.escaped-nul")
        self.cases[idx]["expectations"]["events"]["events"][4] = '=VAL "a' + ch + "b"
        self.save()
        return self.errors()

    def test_raw_escaped_characters_in_event_text(self):
        # The notation escapes NUL, BS, TAB, LF, and CR; a raw one is a notation error.
        for ch in "\x00\x08\x09\x0a\x0d":
            with self.subTest(ch=hex(ord(ch))):
                errs = self.with_event_char(ch)
                # A raw LF already fails the event pattern; the others reach the escape check.
                self.assertTrue(
                    [e for e in errs if "raw NUL, BS, TAB, LF, or CR" in e or "notation" in e], hex(ord(ch))
                )

    def test_other_control_characters_stay_raw(self):
        # BEL, VT, FF, ESC, and DEL are printed as themselves in the pinned notation.
        for ch in "\x07\x0b\x0c\x1b\x7f":
            with self.subTest(ch=hex(ord(ch))):
                self.assertFalse([e for e in self.with_event_char(ch) if "event text" in e], hex(ord(ch)))

    def test_item_index_out_of_range(self):
        self.mutate(
            self.anchored("yaml.anchors.r12-seq-item"),
            lambda c: c["expectations"]["node_locations"]["spans"][0].update(path=[{"item": 2}]),
        )
        self.assertRejected("does not resolve")

    def test_profile_bound_twice_is_ambiguous(self):
        def twice(c):
            c["expectations"]["value"].append(copy.deepcopy(c["expectations"]["value"][0]))

        self.mutate(self.anchored(), twice)
        self.assertRejected("need a value expectation with documents")

    def test_profile_bound_to_error(self):
        def error(c):
            c["expectations"]["value"][0] = {
                "profile": "yamlprims-core",
                "profile_revision": 3,
                "error": {"phase": "syntax"},
            }

        self.mutate(self.anchored(), error)
        self.assertRejected("need a value expectation with documents")

    def test_malformed_value_tree_does_not_crash(self):
        def broken(c):
            c["expectations"]["value"][0]["documents"][0]["entries"][0] = ["not-a-node"]

        self.mutate(self.anchored(), broken)
        self.assertRejected("does not resolve")

    def test_leaf_that_is_not_a_node(self):
        def leaf(c):
            c["expectations"]["value"][0]["documents"][0]["entries"][0][1] = "not-a-node"

        self.mutate(self.anchored(), leaf)
        self.assertRejected("does not resolve")

    def test_undefined_node_kind(self):
        # The int value of x is not a kind the node convention defines.
        self.mutate(
            self.anchored(), lambda c: c["expectations"]["node_locations"]["spans"][0].update(path=[{"value": 1}])
        )
        self.assertRejected("int node spans are undefined in yamlprims-node r1")

    def test_profile_must_have_documents(self):
        self.mutate(self.anchored(), lambda c: c["expectations"]["node_locations"].update(profile_revision=2))
        self.assertRejected("need a value expectation with documents")

    def test_event_convention_is_not_a_node_convention(self):
        self.mutate(
            self.anchored(),
            lambda c: c["expectations"]["node_locations"].update(convention="scalar-alias", convention_revision=2),
        )
        self.assertRejected("unknown node convention")

    def test_span_outside_input(self):
        self.mutate(self.anchored(), lambda c: c["expectations"]["node_locations"]["spans"][0].update(end=10**6))
        self.assertRejected("node span [7, 1000000) outside input")

    def test_document_out_of_range(self):
        self.mutate(self.anchored(), lambda c: c["expectations"]["node_locations"]["spans"][0].update(document=1))
        self.assertRejected("document 1 out of range")


def canonical(value):
    return corpus.canonical_json(value)


class TestCaseRejections(CaseRepo):
    def test_classifier_unknown(self):
        self.mutate(0, lambda c: c["classifiers"].update({"sensitivity": "unknown"}))
        self.assertRejected("classifiers must be exactly")

    def test_classifier_synonym(self):
        self.mutate(0, lambda c: c["classifiers"].update({"sensitivity": "public"}))
        self.assertRejected("classifiers must be exactly")

    def test_classifier_blinded(self):
        self.mutate(0, lambda c: c["classifiers"].update({"sensitivity": "2-blinded"}))
        self.assertRejected("classifiers must be exactly")

    def test_access_tier(self):
        self.mutate(0, lambda c: c["classifiers"].update({"access-tier": "internal"}))
        self.assertRejected("classifiers must be exactly")

    def test_missing_classifiers(self):
        self.mutate(0, lambda c: c.pop("classifiers"))
        self.assertRejected("missing classifiers")

    def test_provenance_origin(self):
        self.mutate(0, lambda c: c["provenance"].update({"origin": "redacted"}))
        self.assertRejected("provenance needs origin")

    def test_public_source_needs_upstream(self):
        self.mutate(0, lambda c: c["provenance"].update({"origin": "public-source"}))
        self.assertRejected("needs an upstream")

    def test_hash_mismatch(self):
        self.mutate(0, lambda c: c["input"].update({"sha256": "0" * 64}))
        self.assertRejected("does not match recorded")

    def test_length_mismatch(self):
        self.mutate(0, lambda c: c["input"].update({"bytes": c["input"]["bytes"] + 1}))
        self.assertRejected("does not match recorded")

    def test_fixture_byte_change(self):
        path = os.path.join(self.root, *self.cases[0]["input"]["path"].split("/"))
        with open(path, "ab") as fh:
            fh.write(b"\r")
        self.assertRejected("does not match recorded")

    def test_path_traversal(self):
        self.mutate(0, lambda c: c["input"].update({"path": "fixtures/yaml/../../etc/passwd"}))
        self.assertRejected("unsafe or misplaced")

    def test_path_outside_format_tree(self):
        self.mutate(0, lambda c: c["input"].update({"path": "manifests/cases.jsonl"}))
        self.assertRejected("unsafe or misplaced")

    def test_path_and_recipe(self):
        self.mutate(0, lambda c: c["input"].update({"recipe": "recipes/yaml/x.json"}))
        self.assertRejected("exactly one of path or recipe")

    def test_unreferenced_fixture(self):
        with open(os.path.join(self.root, "fixtures", "yaml", "orphan.yaml"), "wb") as fh:
            fh.write(b"a: 1\n")
        self.assertRejected("not referenced by any case")

    def test_duplicate_id(self):
        self.cases.append(copy.deepcopy(self.cases[0]))
        self.save()
        self.assertRejected("duplicate case id")

    def test_duplicate_json_key(self):
        line = json.dumps(self.cases[0]).encode()
        self.save(raw=line[:-1] + b',"id":"again"}\n')
        self.assertRejected("duplicate JSON key")

    def test_unsupported_schema_version(self):
        self.mutate(0, lambda c: c.update({"schema_version": "case/v2"}))
        self.assertRejected("unsupported schema_version")

    def test_unknown_profile(self):
        self.mutate(0, lambda c: c["expectations"]["value"][0].update({"profile_revision": 9}))
        self.assertRejected("unknown profile")

    def test_unknown_error_phase(self):
        idx = next(i for i, c in enumerate(self.cases) if "error" in c["expectations"]["value"][0])
        self.mutate(idx, lambda c: c["expectations"]["value"][0]["error"].update({"phase": "runtime"}))
        self.assertRejected("unknown error phase")

    def test_valid_without_events(self):
        self.mutate(0, lambda c: c["expectations"]["events"].pop("events"))
        self.assertRejected("valid events need an event list")

    def test_bad_event_notation(self):
        self.mutate(0, lambda c: c["expectations"]["events"]["events"].append("scalar foo"))
        self.assertRejected("valid events need an event list")

    def test_invalid_with_events(self):
        idx = next(i for i, c in enumerate(self.cases) if c["expectations"]["events"]["status"] == "invalid")
        self.mutate(idx, lambda c: c["expectations"]["events"].update({"events": ["+STR", "-STR"]}))
        self.assertRejected("must not list events")

    def add_typed(self, **entry):
        base = {"profile": "yaml-core", "profile_revision": 1, "path": ["enabled"], "target": "bool"}
        base.update(entry)
        self.mutate(
            0,
            lambda c: (
                c["expectations"].setdefault("typed", []).append({k: v for k, v in base.items() if v is not None})
            ),
        )

    def test_typed_valid(self):
        self.add_typed(result={"t": "bool", "v": True})
        self.assertEqual(self.errors(), [])

    def test_typed_unknown_profile(self):
        self.add_typed(profile_revision=9, result={"t": "bool", "v": True})
        self.assertRejected("unknown profile")

    def test_typed_unknown_target(self):
        self.add_typed(target="u7", result={"t": "bool", "v": True})
        self.assertRejected("unknown typed target")

    def test_typed_both_result_and_error(self):
        self.add_typed(result={"t": "bool", "v": True}, error={"phase": "typed"})
        self.assertRejected("exactly one of result or error")

    def test_typed_neither(self):
        self.add_typed()
        self.assertRejected("exactly one of result or error")

    def test_typed_error_phase(self):
        self.add_typed(error={"phase": "runtime"})
        self.assertRejected("unknown error phase")

    def test_typed_bad_path(self):
        self.add_typed(path=["k", -1], result={"t": "bool", "v": True})
        self.assertRejected("typed path")

    def test_typed_bool_in_path(self):
        self.add_typed(path=[True], result={"t": "bool", "v": True})
        self.assertRejected("typed path")

    def located(self):
        return next(i for i, c in enumerate(self.cases) if "locations" in c["expectations"])

    def test_span_on_undefined_event_kind(self):
        self.mutate(
            self.located(),
            lambda c: c["expectations"]["locations"]["spans"].append({"event_index": 2, "start": 0, "end": 1}),
        )
        self.assertRejected("undefined in scalar-alias r1")

    def test_span_outside_input(self):
        self.mutate(self.located(), lambda c: c["expectations"]["locations"]["spans"][0].update({"end": 10**6}))
        self.assertRejected("outside input")

    def test_inverted_span(self):
        self.mutate(self.located(), lambda c: c["expectations"]["locations"]["spans"][0].update({"start": 5, "end": 4}))
        self.assertRejected("outside input")

    def test_span_index_out_of_range(self):
        self.mutate(self.located(), lambda c: c["expectations"]["locations"]["spans"][0].update({"event_index": 999}))
        self.assertRejected("out of range")

    def test_r2_convention_rejects_undefined_kind(self):
        idx = next(
            i
            for i, c in enumerate(self.cases)
            if c["expectations"].get("locations", {}).get("convention_revision") == 2
        )
        undefined = {"event_index": 2, "start": 0, "end": 0}
        self.mutate(idx, lambda c: c["expectations"]["locations"]["spans"].append(undefined))
        self.assertRejected("undefined in scalar-alias r2")

    def test_r2_profiles_cite_tagged_spec(self):
        for name in os.listdir(os.path.join(self.root, "manifests", "profiles")):
            if name.endswith(".r2.json") and name.startswith("yamlprims-core") and "-limits." not in name:
                with open(os.path.join(self.root, "manifests", "profiles", name)) as fh:
                    prof = json.load(fh)
                urls = [c["url"] for c in prof["cites"]]
                self.assertIn(SPEC_V11_URL, urls, name)
                self.assertEqual(prof["policy"]["flow_indentation"], "strict", name)

    def test_unknown_span_convention(self):
        self.mutate(self.located(), lambda c: c["expectations"]["locations"].update({"convention_revision": 999}))
        self.assertRejected("unknown span convention")

    def test_reviewer_must_differ(self):
        self.mutate(0, lambda c: c["review"].update({"status": "reviewed", "reviewer": c["review"]["author"]}))
        self.assertRejected("reviewer distinct")

    def test_profile_schema_version(self):
        path = os.path.join(self.root, "manifests", "profiles", "yaml-core.r1.json")
        with open(path, "rb") as fh:
            doc = json.loads(fh.read())
        doc["schema_version"] = "profile/v9"
        with open(path, "w") as fh:
            json.dump(doc, fh)
        self.assertRejected("unsupported schema_version 'profile/v9'")

    def test_profile_file_name_must_match(self):
        src = os.path.join(self.root, "manifests", "profiles", "yaml-core.r1.json")
        os.rename(src, os.path.join(self.root, "manifests", "profiles", "yaml-core.json"))
        self.assertRejected("file name must be yaml-core.r1.json")


if __name__ == "__main__":
    unittest.main()
