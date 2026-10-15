"""Double-quoted escape sequences: decoded values and malformed escapes (Python 3.9+ stdlib).

Expected values follow YAML 1.2.2 section 5.7 (escaped characters) and 7.3.1
(double-quoted style), with yamlprims specification revision 1.1 section 4.1:
a double-quoted scalar is a String and is never resolved.
https://yaml.org/spec/1.2.2/#57-escaped-characters
https://github.com/3leaps/yamlprims/blob/spec-v1.1/docs/spec/yamlprims-spec.md

Sets, generated in this order (the recipe's "sets" parameter lists them):
  each       every escape alone, then between ASCII text
  ladder     scalars built by cycling through the escapes until the encoded
             text reaches each size; decoded and encoded lengths differ
  malformed  every proper prefix of each escape, closed by a quote, and
             escape letters YAML does not define: all are syntax errors

The decoded text of each escape is written out below by hand, not obtained from
a parser. Each yielded case is (local_id, category, yaml_text, expectation,
typed).
"""

# (escape as written after the backslash, decoded text) -- YAML 1.2.2 [42]-[61]
ESCAPES = [
    ("0", "\x00"),
    ("a", "\x07"),
    ("b", "\x08"),
    ("t", "\x09"),
    ("\t", "\x09"),
    ("n", "\x0a"),
    ("v", "\x0b"),
    ("f", "\x0c"),
    ("r", "\x0d"),
    ("e", "\x1b"),
    (" ", "\x20"),
    ('"', '"'),
    ("/", "/"),
    ("\\", "\\"),
    ("N", "\u0085"),
    ("_", "\u00a0"),
    ("L", "\u2028"),
    ("P", "\u2029"),
    ("x41", "A"),
    ("x7f", "\x7f"),
    ("xe9", "\u00e9"),
    ("xFF", "\u00ff"),
    ("u00e9", "\u00e9"),
    ("u20AC", "\u20ac"),
    ("uFFFD", "\ufffd"),
    ("U0001F600", "\U0001f600"),
    ("U0010FFFF", "\U0010ffff"),
]

# Letters and digits that are not YAML 1.2.2 escapes (YAML 1.1 and JSON-only
# forms included): an error, never passed through.
UNDEFINED = ["c", "d", "g", "q", "z", "'", "1", "8", "X41", "?", "%"]

SIZES = [16, 64, 256, 1024, 4096]


def S(text):
    return {"t": "str", "v": text}


def K(value):
    return {"documents": [{"t": "map", "entries": [[S("k"), value]]}]}


SYNTAX = {"error": {"phase": "syntax"}}


def gen_each():
    for i, (esc, text) in enumerate(ESCAPES, 1):
        yield "e%02d" % i, 'k: "\\%s"\n' % esc, K(S(text))
        yield "m%02d" % i, 'k: "a\\%sz"\n' % esc, K(S("a" + text + "z"))
    # An escaped line break joins lines with nothing between them (7.3.1).
    yield "lb1", 'k: "a\\\n  b"\n', K(S("ab"))
    yield "lb2", 'k: "a \\\n  b"\n', K(S("a b"))
    # An escaped space before a folded break is kept; unescaped trailing space is not.
    yield "lb3", 'k: "a\\ \n  b"\n', K(S("a  b"))


def gen_ladder():
    for size in SIZES:
        encoded, decoded, i = [], [], 0
        while sum(len(e) for e in encoded) < size:
            esc, text = ESCAPES[i % len(ESCAPES)]
            if esc == "\t":  # an escaped tab is kept in "each"; here only printable source
                i += 1
                continue
            encoded.append("\\" + esc)
            decoded.append(text)
            i += 1
        yield "l%05d" % size, 'k: "%s"\n' % "".join(encoded), K(S("".join(decoded)))


def gen_malformed():
    n = 0
    for esc, _text in ESCAPES:
        if esc[0] not in "xuU":
            continue
        for cut in range(1, len(esc)):
            n += 1
            yield "t%03d" % n, 'k: "\\%s"\n' % esc[:cut], SYNTAX
        # The same prefix followed by a non-hex character.
        n += 1
        yield "t%03d" % n, 'k: "\\%sg"\n' % esc[:-1], SYNTAX
    for letter in UNDEFINED:
        n += 1
        yield "t%03d" % n, 'k: "\\%s"\n' % letter, SYNTAX
    # A backslash at the end of input, with no closing quote.
    n += 1
    yield "t%03d" % n, 'k: "abc\\', SYNTAX


SETS = {"each": gen_each, "ladder": gen_ladder, "malformed": gen_malformed}


def generate(parameters):
    for name in parameters["sets"].split(","):
        for local_id, text, expectation in SETS[name]():
            yield local_id, "scalar-scanning", text, expectation, []
