"""Exact vectors for the event notations (DDR-0010), Python 3.9+ stdlib.

Every expected string below is written out by hand. Round trips are tested too,
but they cannot show that both directions share no mistake; the vectors do.
"""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import events  # noqa: E402

YTS, SCE1 = events.YTS, events.SCE1
BS = "\\"


def val(value, style=":", **fields):
    return dict({"kind": "=VAL", "style": style, "value": value}, **fields)


class TestValueVectors(unittest.TestCase):
    # (decoded value, yaml-test-suite spelling, structcorpus-events/1 spelling)
    VECTORS = [
        ("plain", "plain", "plain"),
        ("a" + BS + "b", "a" + BS + BS + "b", "a" + BS + BS + "b"),
        ("\x00", BS + "0", BS + "0"),
        ("\x08", BS + "b", BS + "b"),
        ("\t", BS + "t", BS + "t"),
        ("\n", BS + "n", BS + "n"),
        ("\r", BS + "r", BS + "r"),
        ("\x01", "\x01", BS + "x01"),
        ("\x07", "\x07", BS + "x07"),
        ("\x0b", "\x0b", BS + "x0B"),
        ("\x0c", "\x0c", BS + "x0C"),
        ("\x1b", "\x1b", BS + "x1B"),
        ("\x1f", "\x1f", BS + "x1F"),
        (" ", " ", " "),
        ("~", "~", "~"),
        ("\x7f", "\x7f", BS + "x7F"),
        ("\x80", "\x80", BS + "x80"),
        ("\x85", "\x85", BS + "x85"),
        ("\x9f", "\x9f", BS + "x9F"),
        ("\xa0", "\xa0", "\xa0"),
        ("\u2027", "\u2027", "\u2027"),
        ("\u2028", "\u2028", BS + "u2028"),
        ("\u2029", "\u2029", BS + "u2029"),
        ("\u202a", "\u202a", "\u202a"),
        ("\u00e9\u20ac\U0001f600", "\u00e9\u20ac\U0001f600", "\u00e9\u20ac\U0001f600"),
        # A literal backslash beside text that looks like an escape stays a backslash.
        (BS + "x41", BS + BS + "x41", BS + BS + "x41"),
        (BS + "n", BS + BS + "n", BS + BS + "n"),
        (BS + "u2028", BS + BS + "u2028", BS + BS + "u2028"),
        ("a b\tc", "a b" + BS + "tc", "a b" + BS + "tc"),
        ("", "", ""),
    ]

    def test_encode(self):
        for value, yts, sce1 in self.VECTORS:
            with self.subTest(value=repr(value)):
                self.assertEqual(events.encode_value(value, YTS), yts)
                self.assertEqual(events.encode_value(value, SCE1), sce1)

    def test_decode(self):
        for value, yts, sce1 in self.VECTORS:
            with self.subTest(value=repr(value)):
                self.assertEqual(events.decode_value(sce1, SCE1), value)
                self.assertEqual(events.decode_value(yts, YTS), value)

    def test_every_control_has_one_spelling(self):
        for o in list(range(0x20)) + list(range(0x7F, 0xA0)):
            ch = chr(o)
            enc = events.encode_value(ch, SCE1)
            self.assertTrue(enc.startswith(BS), hex(o))
            self.assertTrue(all(0x20 <= ord(c) < 0x7F for c in enc), hex(o))
            self.assertEqual(events.decode_value(enc, SCE1), ch)


class TestRejections(unittest.TestCase):
    SCE1_BAD = [
        BS + "x0b",  # lowercase hex
        BS + "x00",  # NUL has a short escape
        BS + "x5C",  # the backslash has a short escape
        BS + "x41",  # printable characters are never escaped
        BS + "xA0",  # above the C1 range
        BS + "x8",  # one digit
        BS + "u0041",  # \u is only for U+2028 and U+2029
        BS + "u202A",
        BS + "e",  # YAML's double-quoted escapes are not part of the notation
        BS + "N",
        BS + "L",
        BS + "U0001F600",
        BS,  # truncated
        "\x07",  # raw characters that must be escaped
        "\x85",
        "\u2028",
        "\x00",
    ]
    YTS_BAD = [BS + "x41", BS + "e", BS, "\x00", "\t", "\n"]

    def test_sce1_rejects(self):
        for text in self.SCE1_BAD:
            with self.subTest(text=repr(text)):
                with self.assertRaises(events.NotationError):
                    events.decode_value(text, SCE1)

    def test_yts_rejects(self):
        for text in self.YTS_BAD:
            with self.subTest(text=repr(text)):
                with self.assertRaises(events.NotationError):
                    events.decode_value(text, YTS)

    def test_yts_accepts_raw_controls_it_does_not_escape(self):
        for ch in "\x07\x0b\x0c\x1b\x7f\x85\u2028":
            self.assertEqual(events.decode_value(ch, YTS), ch)

    def test_surrogates_are_never_values(self):
        for notation in events.NOTATIONS:
            with self.assertRaises(events.NotationError):
                events.encode_value("\ud800", notation)


class TestEventVectors(unittest.TestCase):
    # (event string, notation, parsed fields): upstream-shaped events written out by hand.
    VECTORS = [
        ("+STR", YTS, {"kind": "+STR"}),
        ("+DOC ---", YTS, {"kind": "+DOC", "explicit": True}),
        ("-DOC", YTS, {"kind": "-DOC", "explicit": False}),
        ("+MAP {} &a <!t>", YTS, {"kind": "+MAP", "flow": True, "anchor": "a", "tag": "!t"}),
        ("+SEQ [] &key", YTS, {"kind": "+SEQ", "flow": True, "anchor": "key"}),
        ("+SEQ <tag:yaml.org,2002:seq>", YTS, {"kind": "+SEQ", "tag": "tag:yaml.org,2002:seq"}),
        ("=VAL :a b c", YTS, val("a b c")),
        ("=VAL &x <!local> '42", YTS, val("42", "'", anchor="x", tag="!local")),
        ('=VAL "a' + BS + "0b", YTS, val("a\x00b", '"')),
        ("=VAL |line" + BS + "n", YTS, val("line\n", "|")),
        ("=VAL >", YTS, val("", ">")),
        ("=ALI *anchor", YTS, {"kind": "=ALI", "alias": "anchor"}),
        # A backslash in an anchor, alias, or tag is raw text, never an escape.
        ("=VAL &a" + BS + "n :v", YTS, val("v", anchor="a" + BS + "n")),
        ("=ALI *a" + BS + "0", YTS, {"kind": "=ALI", "alias": "a" + BS + "0"}),
        ("=VAL <!a" + BS + "x41> :v", YTS, val("v", tag="!a" + BS + "x41")),
        # Percent escapes in tags are kept as written.
        ("=VAL <tag:example.com,2026:a%20b> :v", YTS, val("v", tag="tag:example.com,2026:a%20b")),
        ('=VAL "bell' + BS + "x07", SCE1, val("bell\x07", '"')),
        ("=VAL :nel" + BS + "x85", SCE1, val("nel\x85")),
        ("=VAL &ls :" + BS + "u2028", SCE1, val("\u2028", anchor="ls")),
        # Spaces are ordinary value characters, including at the end.
        ("=VAL ' a  ", YTS, val(" a  ", "'")),
        # Delimiter lookalikes in a value never end a field: the tag ends at its first '>'.
        ("=VAL <!t> :a>b", YTS, val("a>b", tag="!t")),
        ("=VAL &x <!t> 'a <b> &c *d", YTS, val("a <b> &c *d", "'", anchor="x", tag="!t")),
        ("=VAL :<not> a tag", YTS, val("<not> a tag")),
    ]

    def test_parse(self):
        for text, notation, fields in self.VECTORS:
            with self.subTest(text=repr(text)):
                self.assertEqual(events.parse(text, notation), fields)

    def test_render(self):
        for text, notation, fields in self.VECTORS:
            with self.subTest(text=repr(text)):
                self.assertEqual(events.render(fields, notation), text)

    def test_convert_exact(self):
        self.assertEqual(events.convert('=VAL "a\x07b', YTS, SCE1), '=VAL "a' + BS + "x07b")
        self.assertEqual(events.convert('=VAL "a' + BS + "x07b", SCE1, YTS), '=VAL "a\x07b')
        self.assertEqual(events.convert("=VAL &x <!t> :" + BS + BS, YTS, SCE1), "=VAL &x <!t> :" + BS + BS)
        self.assertEqual(events.convert("+SEQ [] &a", YTS, SCE1), "+SEQ [] &a")

    def test_convert_keeps_structure(self):
        stream = ["+STR", "+DOC", "+MAP", "=VAL :k", '=VAL "\x1b[31m', "=ALI *k", "-MAP", "-DOC", "-STR"]
        out = [events.convert(e, YTS, SCE1) for e in stream]
        self.assertEqual(len(out), len(stream))
        self.assertEqual([e[:4] for e in out], [e[:4] for e in stream])
        self.assertEqual(out[4], '=VAL "' + BS + "x1B[31m")
        self.assertEqual([events.convert(e, SCE1, YTS) for e in out], stream)


class TestDomains(unittest.TestCase):
    def test_tag_with_delimiter_cannot_be_written(self):
        for tag in ("!a>b", "!a b", "!a\tb", ""):
            with self.subTest(tag=repr(tag)):
                with self.assertRaises(events.NotationError):
                    events.render(val("v", tag=tag), YTS)

    def test_names_outside_sce1_domain(self):
        # YAML allows C1 controls in anchor names; structcorpus-events/1 cannot write them.
        self.assertEqual(events.render({"kind": "=ALI", "alias": "a\x85"}, YTS), "=ALI *a\x85")
        with self.assertRaises(events.NotationError):
            events.render({"kind": "=ALI", "alias": "a\x85"}, SCE1)
        with self.assertRaises(events.NotationError):
            events.convert("=VAL &a\u2028 :v", YTS, SCE1)

    def test_names_with_flow_indicators_or_space_are_rejected(self):
        for name in ("a,b", "a[", "a}", "a b", ""):
            with self.subTest(name=repr(name)):
                with self.assertRaises(events.NotationError):
                    events.render({"kind": "=ALI", "alias": name}, YTS)

    def test_malformed_events(self):
        for text in ("+STR x", "+DOC --", "=VAL", "=VAL x", "=VAL <!t :v", "=ALI anchor", "+MAP junk", "+XYZ"):
            with self.subTest(text=repr(text)):
                with self.assertRaises(events.NotationError):
                    events.parse(text, YTS)

    def test_unknown_notation(self):
        with self.assertRaises(events.NotationError):
            events.parse("+STR", "yaml-test-suite/2")


class TestPinnedRunnerOutput(unittest.TestCase):
    """Output captured from libyaml 0.2.5 tests/run-parser-test-suite (release tarball sha256
    fa240dbf262be053f3898006d502d514936c818e422afdcf33921c63bed9bf2e), written out as literals."""

    # Input: k: "\0\a\b\t\n\v\f\r\e\x7f\x85\L\P\\"
    CONTROLS = (
        '=VAL "' + BS + "0\x07" + BS + "b" + BS + "t" + BS + "n\x0b\x0c" + BS + "r\x1b\x7f\x85\u2028\u2029" + BS + BS
    )
    CONTROLS_VALUE = "\x00\x07\x08\t\n\x0b\x0c\r\x1b\x7f\x85\u2028\u2029" + BS
    CONTROLS_SCE1 = (
        '=VAL "'
        + BS
        + "0"
        + BS
        + "x07"
        + BS
        + "b"
        + BS
        + "t"
        + BS
        + "n"
        + BS
        + "x0B"
        + BS
        + "x0C"
        + BS
        + "r"
        + BS
        + "x1B"
        + BS
        + "x7F"
        + BS
        + "x85"
        + BS
        + "u2028"
        + BS
        + "u2029"
        + BS
        + BS
    )

    def test_controls_line(self):
        self.assertEqual(events.render(val(self.CONTROLS_VALUE, '"'), YTS), self.CONTROLS)
        self.assertEqual(events.parse(self.CONTROLS, YTS), val(self.CONTROLS_VALUE, '"'))
        self.assertEqual(events.convert(self.CONTROLS, YTS, SCE1), self.CONTROLS_SCE1)
        self.assertTrue(all(0x20 <= ord(c) < 0x7F for c in self.CONTROLS_SCE1))

    def test_raw_vt_ff_and_separators_survive_only_in_json(self):
        # The runner writes VT, FF, NEL, U+2028, and U+2029 raw, and str.splitlines() breaks on all
        # of them. Corpus records hold each event as a JSON string, so no line splitting applies.
        self.assertGreater(len(self.CONTROLS.splitlines()), 1)
        self.assertEqual(len(events.convert(self.CONTROLS, YTS, SCE1).splitlines()), 1)

    def test_props_and_alias(self):
        # Input: - &x1 !t a>b / - *x1
        self.assertEqual(events.parse("=VAL &x1 <!t> :a>b", YTS), val("a>b", anchor="x1", tag="!t"))
        self.assertEqual(events.parse("=ALI *x1", YTS), {"kind": "=ALI", "alias": "x1"})

    def test_decoded_tag_with_space_is_outside_the_domain(self):
        # Input: !<!a%20b> x. The runner prints the resolved tag, which here contains a space.
        with self.assertRaises(events.NotationError):
            events.parse("=VAL <!a b> :x", YTS)


class TestSelectionAndDisplay(unittest.TestCase):
    def test_selection_rule(self):
        self.assertFalse(events.needs_sce1([val("a\tb\n\x00")]))
        self.assertTrue(events.needs_sce1([val("\x07")]))
        self.assertTrue(events.needs_sce1([{"kind": "+STR"}, val("\u2029")]))
        self.assertFalse(events.needs_sce1([{"kind": "=ALI", "alias": "a"}]))

    def test_display_never_prints_raw_controls_or_invisible_text(self):
        text = '=VAL "\x1b[2J\x85\u2028\u202e\u200b\ufeff ok'
        shown = events.display(text)
        self.assertTrue(all(0x20 <= ord(c) < 0x7F for c in shown), repr(shown))
        self.assertEqual(shown, '=VAL "\\u{001B}[2J\\u{0085}\\u{2028}\\u{202E}\\u{200B}\\u{FEFF} ok')


if __name__ == "__main__":
    unittest.main()
