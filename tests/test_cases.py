"""Case-record validation and canonical JSON tests (Python 3.9+ stdlib)."""

import copy
import hashlib
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
        s = "\u0000\u0008\u0009\u000a\u000c\u000d\u001f\"\\/\u007f€"
        self.assertEqual(corpus.canonical_json(s), '"\\u0000\\b\\t\\n\\f\\r\\u001f\\"\\\\/\u007f€"')

    def test_structure_and_whitespace(self):
        self.assertEqual(corpus.canonical_json({"b": [1, True, None], "a": {}}), '{"a":{},"b":[1,true,null]}')

    def test_rejects_outside_subset(self):
        for value in (1.5, 2 ** 53, "\ud800", {"k": float("nan")}):
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
            self.cases = [json.loads(l) for l in fh.read().splitlines() if l.strip()]

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
        self.assertEqual(layers, {"events", "value", "locations"})


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
        self.mutate(0, lambda c: c["expectations"].setdefault("typed", []).append({k: v for k, v in base.items() if v is not None}))

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
        self.mutate(self.located(), lambda c: c["expectations"]["locations"]["spans"].append({"event_index": 2, "start": 0, "end": 1}))
        self.assertRejected("undefined in scalar-alias r1")

    def test_span_outside_input(self):
        self.mutate(self.located(), lambda c: c["expectations"]["locations"]["spans"][0].update({"end": 10 ** 6}))
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
            if name.endswith(".r2.json") and name.startswith("yamlprims-core"):
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
