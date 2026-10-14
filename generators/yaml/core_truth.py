"""Scalar-resolution and duplicate-key truth generator (Python 3.9+ stdlib).

Expected values are derived from the published yamlprims specification,
revision 1.0, sections 4 and 5.1, independently of any implementation:
https://github.com/3leaps/yamlprims/blob/spec-v1.0/docs/spec/yamlprims-spec.md

Families (selected by the recipe's "family" parameter):
  booleans    every case variant of true/false/null and YAML 1.1 words, by
              position x style x tag
  collisions  sibling keys; duplicate exactly when key equality (5.1) holds
  numbers     integer and float resolution, plain, quoted, and tagged

Each yielded case is (local_id, category, yaml_text, expectation). An
expectation is {"documents": [value]} or {"error": {...}} in the yaml-value/1
notation (DDR-0003). Nothing here reads time, randomness, or the environment.
"""

import itertools
import math
import re
import struct

# ---- Core schema (spec 4.1): full-match patterns, in order ------------------
NULL = {"~", "null", "Null", "NULL", ""}
TRUE = {"true", "True", "TRUE"}
FALSE = {"false", "False", "FALSE"}
INT_DEC = re.compile(r"[-+]?[0-9]+\Z")
INT_OCT = re.compile(r"0o[0-7]+\Z")
INT_HEX = re.compile(r"0x[0-9a-fA-F]+\Z")
FLOAT = re.compile(r"[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?\Z")
INF = re.compile(r"[-+]?(\.inf|\.Inf|\.INF)\Z")
NAN = re.compile(r"(\.nan|\.NaN|\.NAN)\Z")
I128_MIN, U128_MAX = -(2 ** 127), 2 ** 128 - 1


class Fail(Exception):
    def __init__(self, phase, kind=None):
        Exception.__init__(self, phase, kind)
        self.error = {"phase": phase}
        if kind:
            self.error["kind"] = kind


def STR(text):
    return {"t": "str", "v": text}


def INT(n):
    return {"t": "int", "v": str(n)}


def FLT(x):
    bits = "7ff8000000000000" if math.isnan(x) else struct.pack(">d", x).hex()
    return {"t": "float", "bits": bits}


def is_int(t):
    return bool(INT_DEC.match(t) or INT_OCT.match(t) or INT_HEX.match(t))


def parse_int(t):
    if INT_OCT.match(t):
        return int(t[2:], 8)
    if INT_HEX.match(t):
        return int(t[2:], 16)
    return int(t, 10)


def int_value(t):
    n = parse_int(t)
    if n < I128_MIN or n > U128_MAX:
        raise Fail("resolution", "integer_out_of_range")
    return INT(n)


def float_value(t):
    if INF.match(t):
        return FLT(-math.inf if t.startswith("-") else math.inf)
    if NAN.match(t):
        return FLT(math.nan)
    x = float(t)  # correctly rounded, ties to even; underflow rounds to nearest
    if math.isinf(x):
        raise Fail("resolution", "float_out_of_range")
    return FLT(x)


def core_plain(t):
    if t in NULL:
        return {"t": "null"}
    if t in TRUE:
        return {"t": "bool", "v": True}
    if t in FALSE:
        return {"t": "bool", "v": False}
    if is_int(t):
        return int_value(t)
    if FLOAT.match(t) or INF.match(t) or NAN.match(t):
        return float_value(t)
    return STR(t)


def resolve(text, plain, tag):
    """Spec 4.1, 4.3, 4.4 for one scalar. tag is None or the tag as written."""
    if tag is None:
        return core_plain(text) if plain else STR(text)
    if tag in ("!!str", "!"):
        return STR(text)
    if tag == "!!null":
        if text in NULL:
            return {"t": "null"}
        raise Fail("resolution", "tag_value_mismatch")
    if tag == "!!bool":
        if text in TRUE:
            return {"t": "bool", "v": True}
        if text in FALSE:
            return {"t": "bool", "v": False}
        raise Fail("resolution", "tag_value_mismatch")
    if tag == "!!int":
        if is_int(text):
            return int_value(text)
        raise Fail("resolution", "tag_value_mismatch")
    if tag == "!!float":
        if is_int(text):
            n = parse_int(text)
            if float(n) != n:
                raise Fail("resolution", "tag_value_mismatch")
            return FLT(float(n))
        if FLOAT.match(text) or INF.match(text) or NAN.match(text):
            return float_value(text)
        raise Fail("resolution", "tag_value_mismatch")
    if tag.startswith("!") and not tag.startswith("!!"):
        return {"t": "tagged", "tag": tag, "inner": STR(text)}  # 4.4: raw String inner
    raise ValueError(tag)


# ---- booleans ---------------------------------------------------------------
def case_variants(w):
    out = set()
    for mask in itertools.product([0, 1], repeat=len(w)):
        out.add("".join(c.upper() if m else c.lower() for c, m in zip(w, mask)))
    return sorted(out)


WORDS = []
for _w in ["true", "false", "null", "y", "yes", "n", "no", "on", "off"]:
    WORDS += case_variants(_w)
WORDS += ["~", "", "1", "0"]

STYLES = ["plain", "single", "double", "literal", "literal_strip", "literal_keep",
          "folded", "folded_strip", "folded_keep"]
BLOCK = {"literal": "|", "literal_strip": "|-", "literal_keep": "|+",
         "folded": ">", "folded_strip": ">-", "folded_keep": ">+"}
TAGS = [None, "!!bool", "!!str", "!!null", "!", "!custom"]
POSITIONS = ["block_value", "block_implicit_key", "block_explicit_key", "block_seq",
             "flow_seq", "flow_key", "flow_value", "top"]
KEY_POSITIONS = {"block_implicit_key", "block_explicit_key", "flow_key"}
FLOW_POSITIONS = {"flow_seq", "flow_key", "flow_value"}


def dq(word):
    """Double-quoted form. Words are printable ASCII without quote or backslash."""
    assert all(0x20 <= ord(c) < 0x7F and c not in '"\\' for c in word), word
    return '"' + word + '"'


def inline(word, style, tag):
    body = {"plain": word, "single": "'" + word + "'", "double": dq(word)}[style]
    return (tag + " " + body) if tag else body


def block_head(style, tag):
    return (tag + " " if tag else "") + BLOCK[style]


def document(word, style, tag, pos):
    """YAML text and validity for one row, or None when the row is not generated."""
    block = style in BLOCK
    if word == "" and (pos in KEY_POSITIONS or pos in ("flow_seq", "top")) and style == "plain":
        return None  # an empty plain key, item, or document is a different construct
    if block and word == "":
        return None
    if block:
        head = block_head(style, tag)
        if pos in FLOW_POSITIONS or pos == "block_implicit_key":
            # Block scalars cannot appear in flow context or as implicit keys.
            y = {"flow_seq": "[%s\n  %s\n]\n", "flow_key": "{%s\n  %s\n: v}\n",
                 "flow_value": "{k: %s\n  %s\n}\n", "block_implicit_key": "%s\n  %s\n: v\n"}[pos]
            return y % (head, word), False
        y = {"block_value": "k: %s\n  %s\n", "block_explicit_key": "? %s\n  %s\n: v\n",
             "block_seq": "- %s\n  %s\n", "top": "%s\n  %s\n"}[pos]
        return y % (head, word), True
    s = inline(word, style, tag)
    if style == "plain" and word == "" and tag:
        s = tag  # tag with empty plain content
    y = {"block_value": "k: %s\n", "block_implicit_key": "%s: v\n", "block_explicit_key": "? %s\n: v\n",
         "block_seq": "- %s\n", "flow_seq": "[%s]\n", "flow_key": "{%s: v}\n",
         "flow_value": "{k: %s}\n", "top": "%s\n"}[pos]
    return y % s, True


def block_text(word, style):
    """Single content line at end of input: clip and keep end with one break, strip with none."""
    return word if BLOCK[style].endswith("-") else word + "\n"


def wrap(pos, v):
    """Place the scalar's value in the document the position template builds."""
    if pos in ("block_value", "flow_value"):
        return {"t": "map", "entries": [[STR("k"), v]]}
    if pos in KEY_POSITIONS:
        return {"t": "map", "entries": [[v, STR("v")]]}
    if pos in ("block_seq", "flow_seq"):
        return {"t": "seq", "items": [v]}
    return v


def gen_booleans():
    n = 0
    for word, style, tag, pos in itertools.product(WORDS, STYLES, TAGS, POSITIONS):
        d = document(word, style, tag, pos)
        if d is None:
            continue
        y, valid = d
        n += 1
        rid = "b%05d" % n
        if not valid:
            yield rid, "syntax", y, {"error": {"phase": "syntax"}}
            continue
        text = block_text(word, style) if style in BLOCK else word
        try:
            v = resolve(text, style == "plain", tag)
        except Fail as f:
            yield rid, "scalar-resolution", y, {"error": f.error}
            continue
        yield rid, "scalar-resolution", y, {"documents": [wrap(pos, v)]}


# ---- collisions (spec 5.1, 5.2) ---------------------------------------------
def gen_collisions():
    keys = [(w, st) for w in WORDS if w != "" for st in ("plain", "double")]
    n = 0
    for (w1, s1), (w2, s2) in itertools.combinations(keys, 2):
        v1, v2 = resolve(w1, s1 == "plain", None), resolve(w2, s2 == "plain", None)
        y = "%s: 1\n%s: 2\n" % (inline(w1, s1, None), inline(w2, s2, None))
        n += 1
        rid = "c%05d" % n
        if v1 == v2:  # key equality over these scalar kinds is value equality
            yield rid, "duplicate-keys", y, {"error": {"phase": "structure", "kind": "duplicate_key"}}
        else:
            yield rid, "duplicate-keys", y, {"documents": [{"t": "map", "entries": [[v1, INT(1)], [v2, INT(2)]]}]}


# ---- numbers ----------------------------------------------------------------
NUM_TEXTS = [
    "0", "1", "-1", "+1", "007", "-0", "+0", "0o17", "0o8", "0x1F", "0xff", "0XFF", "-0x1", "0b101",
    "1_000", "1.0", "1.", ".5", "-.5", "1e3", "1E3", "1e+3", "1.5e-3", "-0.0", "0.0", "1e9999", "-1e9999",
    "1e-400", "2.5e-324", "4.9e-324", "3.4028235e38", "3.5e38", "1e39", "16777217", "9007199254740993",
    ".inf", "-.inf", "+.inf", ".Inf", ".INF", ".nan", ".NaN", ".NAN", "inf", "nan", "-.nan",
    "127", "128", "-128", "-129", "255", "256", "65535", "65536", "4294967295", "4294967296",
    "18446744073709551615", "18446744073709551616", "-9223372036854775808", "-9223372036854775809",
    str(U128_MAX), str(U128_MAX + 1), str(I128_MIN), str(I128_MIN - 1),
    str(2 ** 127 - 1), str(2 ** 127), "1:20", "0755",
    # binary32 overflow threshold 2^128 - 2^103 and its neighbors, both signs (spec 8)
    "3.4028234663852886e38", "-3.4028235e38", "3.4028235677973362e38", "3.4028235677973366e38",
    "-3.4028235677973362e38", "-3.4028235677973366e38", "3.4028236e38",
]
NUM_FORMS = [("plain", None), ("double", None), ("double", "!!int"), ("plain", "!!float"), ("plain", "!!str")]


def gen_numbers():
    n = 0
    for t in NUM_TEXTS:
        for style, tag in NUM_FORMS:
            y = "k: " + inline(t, style, tag) + "\n"
            n += 1
            rid = "n%04d" % n
            try:
                v = resolve(t, style == "plain", tag)
            except Fail as f:
                yield rid, "numeric-resolution", y, {"error": f.error}
                continue
            yield rid, "numeric-resolution", y, {"documents": [wrap("block_value", v)]}


FAMILIES = {"booleans": gen_booleans, "collisions": gen_collisions, "numbers": gen_numbers}


def generate(parameters):
    return FAMILIES[parameters["family"]]()
