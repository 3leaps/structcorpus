"""Hand-checked boundary goldens for the yamlprims-core profiles (Python 3.9+ stdlib).

Every expected value below is written out by hand from the published yamlprims
specification revision 1.0, not computed by a resolver:
https://github.com/3leaps/yamlprims/blob/spec-v1.0/docs/spec/yamlprims-spec.md

They anchor the generated truth tables (core_truth.py) and cover what those
tables do not reach: merge policies, aliases, composite and tagged keys,
documents, and typed targets on structured inputs.

Each row: (local_id, category, merge_policy, yaml_text, expectation, typed).
merge_policy selects the profile: "reject" -> yamlprims-core,
"apply" -> yamlprims-core-merge-apply, "as-key" -> yamlprims-core-merge-as-key.
"""

NULL = {"t": "null"}
TRUE = {"t": "bool", "v": True}
FALSE = {"t": "bool", "v": False}


def S(v):
    return {"t": "str", "v": v}


def I(n):
    return {"t": "int", "v": str(n)}


def F(bits):
    return {"t": "float", "bits": bits}


def T(tag, inner):
    return {"t": "tagged", "tag": tag, "inner": inner}


def SEQ(*items):
    return {"t": "seq", "items": list(items)}


def MAP(*pairs):
    return {"t": "map", "entries": [list(p) for p in pairs]}


def K(v):
    """Document {k: v}."""
    return {"documents": [MAP((S("k"), v))]}


def DOC(v):
    return {"documents": [v]}


def ERR(phase, kind=None):
    e = {"phase": phase}
    if kind:
        e["kind"] = kind
    return {"error": e}


def TY(target, result=None, error=None, path=("k",)):
    entry = {"path": list(path), "target": target}
    if error is not None:
        entry["error"] = error
    else:
        entry["result"] = result
    return entry


TYPE = {"phase": "typed", "kind": "type"}

ROWS = [
    # 4.1 Core booleans and nulls
    ("g001", "scalar-resolution", "reject", "k: true\n", K(TRUE), []),
    ("g002", "scalar-resolution", "reject", "k: True\n", K(TRUE), []),
    ("g003", "scalar-resolution", "reject", "k: TRUE\n", K(TRUE), []),
    ("g004", "scalar-resolution", "reject", "k: tRUE\n", K(S("tRUE")), []),
    ("g005", "scalar-resolution", "reject", "k: false\n", K(FALSE), []),
    ("g006", "scalar-resolution", "reject", "k: FALSE\n", K(FALSE), []),
    ("g007", "scalar-resolution", "reject", "k: fALSE\n", K(S("fALSE")), []),
    ("g008", "scalar-resolution", "reject", "k: yes\n", K(S("yes")), []),
    ("g009", "scalar-resolution", "reject", "k: Yes\n", K(S("Yes")), []),
    ("g010", "scalar-resolution", "reject", "k: on\n", K(S("on")), []),
    ("g011", "scalar-resolution", "reject", "k: OFF\n", K(S("OFF")), []),
    ("g012", "scalar-resolution", "reject", "k: y\n", K(S("y")), []),
    ("g013", "scalar-resolution", "reject", "k: n\n", K(S("n")), []),
    ("g014", "scalar-resolution", "reject", "k: no\n", K(S("no")), []),
    ("g015", "scalar-resolution", "reject", "y: 1\n", DOC(MAP((S("y"), I(1)))), []),
    ("g016", "scalar-resolution", "reject", "yes: 1\n", DOC(MAP((S("yes"), I(1)))), []),
    ("g017", "scalar-resolution", "reject", "true: 1\n", DOC(MAP((TRUE, I(1)))), []),
    ("g018", "scalar-resolution", "reject", "k: ~\n", K(NULL), []),
    ("g019", "scalar-resolution", "reject", "k: null\n", K(NULL), []),
    ("g020", "scalar-resolution", "reject", "k: Null\n", K(NULL), []),
    ("g021", "scalar-resolution", "reject", "k: NULL\n", K(NULL), []),
    ("g022", "scalar-resolution", "reject", "k: nULL\n", K(S("nULL")), []),
    ("g023", "scalar-resolution", "reject", "k:\n", K(NULL), []),
    ("g024", "scalar-resolution", "reject", "k: ''\n", K(S("")), []),
    ("g025", "scalar-resolution", "reject", 'k: "true"\n', K(S("true")), []),
    ("g026", "scalar-resolution", "reject", "k: 'false'\n", K(S("false")), []),
    ("g027", "scalar-resolution", "reject", "k: |\n  true\n", K(S("true\n")), []),
    ("g028", "scalar-resolution", "reject", "k: |-\n  true\n", K(S("true")), []),
    ("g029", "scalar-resolution", "reject", "k: >-\n  null\n", K(S("null")), []),
    ("g030", "scalar-resolution", "reject", "? |-\n  true\n: v\n", DOC(MAP((S("true"), S("v")))), []),
    ("g031", "scalar-resolution", "reject", "? >\n  key\n: v\n", DOC(MAP((S("key\n"), S("v")))), []),
    ("g032", "scalar-resolution", "reject", "[true, yes, ~]\n", DOC(SEQ(TRUE, S("yes"), NULL)), []),
    ("g034", "scalar-resolution", "reject", "{true: 1}\n", DOC(MAP((TRUE, I(1)))), []),
    ("g035", "scalar-resolution", "reject", "true\n", DOC(TRUE), []),
    ("g036", "documents", "reject", "", DOC(NULL), []),
    ("g037", "documents", "reject", "# only a comment\n", DOC(NULL), []),
    # 4.1 numbers
    ("g038", "numeric-resolution", "reject", "k: 42\n", K(I(42)), []),
    ("g039", "numeric-resolution", "reject", "k: -42\n", K(I(-42)), []),
    ("g040", "numeric-resolution", "reject", "k: +42\n", K(I(42)), []),
    ("g041", "numeric-resolution", "reject", "k: 0042\n", K(I(42)), []),
    ("g042", "numeric-resolution", "reject", "k: 0755\n", K(I(755)), []),
    ("g043", "numeric-resolution", "reject", "k: 0o17\n", K(I(15)), []),
    ("g044", "numeric-resolution", "reject", "k: 0x1F\n", K(I(31)), []),
    ("g045", "numeric-resolution", "reject", "k: -0x1\n", K(S("-0x1")), []),
    ("g046", "numeric-resolution", "reject", "k: 0b101\n", K(S("0b101")), []),
    ("g047", "numeric-resolution", "reject", "k: 1_000\n", K(S("1_000")), []),
    ("g048", "numeric-resolution", "reject", "k: 1:20\n", K(S("1:20")), []),
    ("g049", "numeric-resolution", "reject", "k: 340282366920938463463374607431768211455\n",
     K(I(340282366920938463463374607431768211455)), []),
    ("g050", "numeric-resolution", "reject", "k: 340282366920938463463374607431768211456\n",
     ERR("resolution", "integer_out_of_range"), []),
    ("g051", "numeric-resolution", "reject", "k: -170141183460469231731687303715884105728\n",
     K(I(-170141183460469231731687303715884105728)), []),
    ("g052", "numeric-resolution", "reject", "k: -170141183460469231731687303715884105729\n",
     ERR("resolution", "integer_out_of_range"), []),
    ("g053", "numeric-resolution", "reject", "k: 1.5\n", K(F("3ff8000000000000")), []),
    ("g054", "numeric-resolution", "reject", "k: 1.\n", K(F("3ff0000000000000")), []),
    ("g055", "numeric-resolution", "reject", "k: .5\n", K(F("3fe0000000000000")), []),
    ("g056", "numeric-resolution", "reject", "k: 1e3\n", K(F("408f400000000000")), []),
    ("g057", "numeric-resolution", "reject", "k: -0.0\n", K(F("8000000000000000")), []),
    ("g058", "numeric-resolution", "reject", "k: 1e9999\n", ERR("resolution", "float_out_of_range"), []),
    ("g059", "numeric-resolution", "reject", "k: 1e-400\n", K(F("0000000000000000")), []),
    ("g060", "numeric-resolution", "reject", "k: .inf\n", K(F("7ff0000000000000")), []),
    ("g061", "numeric-resolution", "reject", "k: -.Inf\n", K(F("fff0000000000000")), []),
    ("g062", "numeric-resolution", "reject", "k: +.INF\n", K(F("7ff0000000000000")), []),
    ("g063", "numeric-resolution", "reject", "k: .nan\n", K(F("7ff8000000000000")), []),
    ("g064", "numeric-resolution", "reject", "k: .NaN\n", K(F("7ff8000000000000")), []),
    ("g065", "numeric-resolution", "reject", "k: -.nan\n", K(S("-.nan")), []),
    ("g066", "numeric-resolution", "reject", "k: inf\n", K(S("inf")), []),
    ("g067", "numeric-resolution", "reject", 'k: "8080"\n', K(S("8080")), []),
    # 4.3 explicit core tags
    ("g068", "tags", "reject", 'k: !!int "42"\n', K(I(42)), []),
    ("g069", "tags", "reject", 'k: !!int "abc"\n', ERR("resolution", "tag_value_mismatch"), []),
    ("g070", "tags", "reject", 'k: !!bool "TRUE"\n', K(TRUE), []),
    ("g071", "tags", "reject", 'k: !!bool "yes"\n', ERR("resolution", "tag_value_mismatch"), []),
    ("g072", "tags", "reject", "k: !!str 42\n", K(S("42")), []),
    ("g073", "tags", "reject", "k: !!str true\n", K(S("true")), []),
    ("g074", "tags", "reject", "k: !!float 1\n", K(F("3ff0000000000000")), []),
    ("g075", "tags", "reject", 'k: !!null ""\n', K(NULL), []),
    ("g076", "tags", "reject", "k: !!null x\n", ERR("resolution", "tag_value_mismatch"), []),
    ("g077", "tags", "reject", "k: !!seq [1]\n", K(SEQ(I(1))), []),
    ("g078", "tags", "reject", "k: !!map [1]\n", ERR("resolution", "tag_kind_mismatch"), []),
    ("g079", "tags", "reject", "k: !!int [1]\n", ERR("resolution", "tag_kind_mismatch"), []),
    ("g080", "tags", "reject", "k: !<tag:yaml.org,2002:int> 7\n", K(I(7)), []),
    # 4.4 non-specific and non-core tags
    ("g081", "tags", "reject", "k: ! 42\n", K(S("42")), []),
    ("g082", "tags", "reject", "k: ! true\n", K(S("true")), []),
    ("g083", "tags", "reject", "k: !custom 42\n", K(T("!custom", S("42"))), []),
    ("g084", "tags", "reject", "k: !custom true\n", K(T("!custom", S("true"))), []),
    ("g085", "tags", "reject", "k: !<tag:example.com,2026:thing> x\n",
     K(T("tag:example.com,2026:thing", S("x"))), []),
    ("g086", "tags", "reject", "%TAG !e! tag:example.com,2026:\n---\nk: !e!thing x\n",
     K(T("tag:example.com,2026:thing", S("x"))), []),
    ("g087", "tags", "reject", "k: !!binary aGk=\n", K(T("tag:yaml.org,2002:binary", S("aGk="))), []),
    ("g088", "tags", "reject", "k: !!timestamp 2001-12-14\n",
     K(T("tag:yaml.org,2002:timestamp", S("2001-12-14"))), []),
    ("g089", "tags", "reject", "k: !custom [!inner x]\n", K(T("!custom", SEQ(T("!inner", S("x"))))), []),
    # 5.1 / 5.2 key equality and duplicates
    ("g090", "duplicate-keys", "reject", "a: 1\na: 2\n", ERR("structure", "duplicate_key"), []),
    ("g091", "duplicate-keys", "reject", "1: a\n0x1: b\n", ERR("structure", "duplicate_key"), []),
    ("g092", "duplicate-keys", "reject", "1: a\n'1': b\n", DOC(MAP((I(1), S("a")), (S("1"), S("b")))), []),
    ("g093", "duplicate-keys", "reject", "1: a\n1.0: b\n",
     DOC(MAP((I(1), S("a")), (F("3ff0000000000000"), S("b")))), []),
    ("g094", "duplicate-keys", "reject", "true: a\nTrue: b\n", ERR("structure", "duplicate_key"), []),
    ("g095", "duplicate-keys", "reject", "yes: a\nYes: b\n", DOC(MAP((S("yes"), S("a")), (S("Yes"), S("b")))), []),
    ("g096", "duplicate-keys", "reject", "~: a\nnull: b\n", ERR("structure", "duplicate_key"), []),
    ("g097", "duplicate-keys", "reject", "0.0: a\n-0.0: b\n", ERR("structure", "duplicate_key"), []),
    ("g098", "duplicate-keys", "reject", "? {a: 1, b: 2}\n: x\n? {b: 2, a: 1}\n: y\n",
     ERR("structure", "duplicate_key"), []),
    ("g099", "duplicate-keys", "reject", "? [1, 2]\n: x\n? [2, 1]\n: y\n",
     DOC(MAP((SEQ(I(1), I(2)), S("x")), (SEQ(I(2), I(1)), S("y")))), []),
    ("g100", "duplicate-keys", "reject", "!a x: 1\n!b x: 2\n",
     DOC(MAP((T("!a", S("x")), I(1)), (T("!b", S("x")), I(2)))), []),
    ("g101", "duplicate-keys", "reject", "!a x: 1\n!<!a> x: 2\n", ERR("structure", "duplicate_key"), []),
    ("g102", "duplicate-keys", "reject", "? .nan\n: 1\n", ERR("structure", "invalid_key"), []),
    ("g103", "duplicate-keys", "reject", "? [.nan]\n: 1\n", ERR("structure", "invalid_key"), []),
    # 5.3 merge
    ("g104", "merge-policy", "reject", "b: &b {x: 1}\nm: {<<: *b}\n", ERR("structure", "merge_rejected"), []),
    ("g105", "merge-policy", "apply", "b: &b {x: 1, y: 1}\nm: {y: 2, <<: *b}\n",
     DOC(MAP((S("b"), MAP((S("x"), I(1)), (S("y"), I(1)))), (S("m"), MAP((S("y"), I(2)), (S("x"), I(1)))))), []),
    ("g107", "merge-policy", "apply", "b: &b {x: 1, y: 1}\nm: {<<: *b, y: 2}\n",
     DOC(MAP((S("b"), MAP((S("x"), I(1)), (S("y"), I(1)))), (S("m"), MAP((S("x"), I(1)), (S("y"), I(2)))))), []),
    ("g108", "merge-policy", "apply", "p: &p {x: 1}\nq: &q {x: 2, z: 2}\nm: {<<: [*p, *q]}\n",
     DOC(MAP((S("p"), MAP((S("x"), I(1)))), (S("q"), MAP((S("x"), I(2)), (S("z"), I(2)))),
             (S("m"), MAP((S("x"), I(1)), (S("z"), I(2)))))), []),
    ("g110", "merge-policy", "apply", "m: {<<: 1}\n", ERR("structure", "merge_source"), []),
    ("g111", "merge-policy", "apply", "b: &b {x: 1}\nm: {<<: *b, <<: *b}\n", ERR("structure", "duplicate_key"), []),
    ("g112", "merge-policy", "apply", 'b: &b {x: 1}\nm: {"<<": *b}\n',
     DOC(MAP((S("b"), MAP((S("x"), I(1)))), (S("m"), MAP((S("<<"), MAP((S("x"), I(1)))))))), []),
    ("g113", "merge-policy", "apply", "b: &b {x: 1}\nm: {!!str <<: *b}\n",
     DOC(MAP((S("b"), MAP((S("x"), I(1)))), (S("m"), MAP((S("<<"), MAP((S("x"), I(1)))))))), []),
    ("g114", "merge-policy", "apply", 'b: &b {x: 1}\nm: {!!merge "<<": *b}\n',
     DOC(MAP((S("b"), MAP((S("x"), I(1)))), (S("m"), MAP((S("x"), I(1)))))), []),
    ("g115", "merge-policy", "as-key", "b: &b {x: 1}\nm: {<<: *b}\n",
     DOC(MAP((S("b"), MAP((S("x"), I(1)))), (S("m"), MAP((S("<<"), MAP((S("x"), I(1)))))))), []),
    # 5.4 aliases
    ("g116", "aliases", "reject", "a: &x 1\nb: *x\n", DOC(MAP((S("a"), I(1)), (S("b"), I(1)))), []),
    ("g117", "aliases", "reject", "a: *x\n", ERR("structure", "unknown_anchor"), []),
    ("g118", "aliases", "reject", "a: &x 1\nb: &x 2\nc: *x\n",
     DOC(MAP((S("a"), I(1)), (S("b"), I(2)), (S("c"), I(2)))), []),
    # 5.5 documents
    ("g119", "documents", "reject", "a: 1\n---\nb: 2\n", ERR("structure", "multiple_documents"), []),
    # 8 typed conversion
    ("g120", "typed", "reject", "k: 8080\n", K(I(8080)), [TY("u16", result=I(8080))]),
    ("g121", "typed", "reject", 'k: "8080"\n', K(S("8080")), [TY("u16", error=TYPE)]),
    ("g122", "typed", "reject", "k: 70000\n", K(I(70000)),
     [TY("u16", error={"phase": "typed", "kind": "integer_out_of_range"})]),
    ("g123", "typed", "reject", "k: 1.0\n", K(F("3ff0000000000000")), [TY("u16", error=TYPE)]),
    ("g124", "typed", "reject", "k: !custom 1\n", K(T("!custom", S("1"))), [TY("u16", error=TYPE)]),
    ("g125", "typed", "reject", "k: yes\n", K(S("yes")), [TY("bool", error=TYPE)]),
    ("g126", "typed", "reject", "k: 1\n", K(I(1)), [TY("string", error=TYPE)]),
    ("g127", "typed", "reject", "k: ~\n", K(NULL), [TY("string", error=TYPE), TY("option-bool", result={"t": "none"})]),
    ("g129", "typed", "reject", "k: !!null ~\n", K(NULL), [TY("option-bool", result={"t": "none"})]),
]

PROFILES = {"reject": "yamlprims-core", "apply": "yamlprims-core-merge-apply", "as-key": "yamlprims-core-merge-as-key"}


def generate(parameters):
    """Yield the rows for one merge policy."""
    policy = parameters["merge_policy"]
    for local_id, category, merge, text, expectation, typed in ROWS:
        if merge == policy:
            yield local_id, category, text, expectation, typed
