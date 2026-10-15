"""Tag-heavy trees: retained-tag values and wrapper accounting (Python 3.9+ stdlib).

Expected values follow the published yamlprims specification revision 1.1,
sections 3, 4.4, and 6:
https://github.com/3leaps/yamlprims/blob/spec-v1.1/docs/spec/yamlprims-spec.md

Sets (selected by the recipe's "set" parameter):
  values  many tiny tagged scalars, tagged collections, tags on keys, nested
          tags, and core tags beside non-core ones (yamlprims-core)
  limits  inputs one below, at, and one above max_nodes and max_owned_bytes
          of the yamlprims-core-limits profile, where each retained tag adds
          a wrapper node (6)

Only shorthand local tags (!name) are used. YAML 1.2.2 section 6.8.2 fixes
their handle ("!") and suffix ("name"), and the uri is "!name", so the tag
bytes of section 6 are 2 + 2 * len(name). Verbatim tags are avoided: their
handle and suffix are not fixed by YAML.

Each yielded case is (local_id, category, yaml_text, expectation, typed).
"""

NODE = 64  # section 6: per-node charge
ENTRY = 24  # section 6: per mapping entry


def S(v):
    return {"t": "str", "v": v}


def T(name, inner):
    return {"t": "tagged", "tag": "!" + name, "inner": inner}


def SEQ(items):
    return {"t": "seq", "items": list(items)}


def MAP(pairs):
    return {"t": "map", "entries": [[k, v] for k, v in pairs]}


def DOC(v):
    return {"documents": [v]}


def tag_bytes(name):
    """uri "!name" + handle "!" + suffix "name" (section 6)."""
    return (1 + len(name)) + 1 + len(name)


def weight(v):
    """Section 6 owned-byte weight of a value in the yaml-value/1 notation."""
    t = v["t"]
    if t == "str":
        return NODE + len(v["v"].encode("utf-8"))
    if t == "tagged":
        return NODE + tag_bytes(v["tag"][1:]) + weight(v["inner"])
    if t == "seq":
        return NODE + sum(weight(i) for i in v["items"])
    if t == "map":
        return NODE + ENTRY * len(v["entries"]) + sum(weight(k) + weight(x) for k, x in v["entries"])
    if t in ("null", "bool", "int", "float"):
        return NODE
    raise ValueError(t)


def nodes(v):
    """Section 6 node count: a retained tag is a wrapper node over its inner node."""
    t = v["t"]
    if t == "tagged":
        return 1 + nodes(v["inner"])
    if t == "seq":
        return 1 + sum(nodes(i) for i in v["items"])
    if t == "map":
        return 1 + sum(nodes(k) + nodes(x) for k, x in v["entries"])
    return 1


def gen_values():
    for n in (10, 100, 1000, 10000):
        text = "[" + ", ".join("!t x" for _ in range(n)) + "]\n"
        yield "seq%05d" % n, text, DOC(SEQ(T("t", S("x")) for _ in range(n)))
    # Tags on collections, keys, and values; children of a tagged collection resolve normally (4.4).
    yield (
        "nested",
        "!m {!k a: !s [!i 1, 2, !e ''], b: !n {}}\n",
        DOC(
            T(
                "m",
                MAP(
                    [
                        (T("k", S("a")), T("s", SEQ([T("i", S("1")), {"t": "int", "v": "2"}, T("e", S(""))]))),
                        (S("b"), T("n", MAP([]))),
                    ]
                ),
            )
        ),
    )
    # Core tags direct resolution and add no wrapper; a non-core tag keeps raw text.
    yield (
        "core-beside",
        "[!!int '7', !seven 7, !!str 7, ! 7, !!seq [!x 7]]\n",
        DOC(SEQ([{"t": "int", "v": "7"}, T("seven", S("7")), S("7"), S("7"), SEQ([T("x", S("7"))])])),
    )
    # The same scalar under two different tags is two different keys (5.1).
    yield (
        "keys-differ",
        "!a x: 1\n!b x: 2\n",
        DOC(MAP([(T("a", S("x")), {"t": "int", "v": "1"}), (T("b", S("x")), {"t": "int", "v": "2"})])),
    )
    yield "keys-equal", "!a x: 1\n!a x: 2\n", {"error": {"phase": "structure", "kind": "duplicate_key"}}
    # A long tag on a tiny scalar.
    name = "t" * 1000
    yield "long-tag", "!%s x\n" % name, DOC(T(name, S("x")))


def limit_rows(budget_name, limit, build):
    """Rows whose measure is limit - 1, limit, and limit + 1; only the last fails."""
    for delta in (-1, 0, 1):
        text, value, measure = build(limit + delta)
        assert measure == limit + delta, (budget_name, measure, limit + delta)
        failure = {"phase": "limit", "kind": "limit_exceeded", "limit": budget_name}
        expectation = DOC(value) if delta <= 0 else {"error": failure}
        yield "%s-%s" % (budget_name.replace("_", "-"), ("below", "at", "above")[delta + 1]), text, expectation


def by_nodes(target):
    """A flow sequence of tagged scalars, plus one plain scalar when target is even."""
    pairs, extra = divmod(target - 1, 2)
    items = [T("t", S("x"))] * pairs + [S("y")] * extra
    text = "[" + ", ".join(["!t x"] * pairs + ["y"] * extra) + "]\n"
    value = SEQ(items)
    return text, value, nodes(value)


def by_weight(target):
    """Eight tagged scalars with 200-byte tag names; content lengths set the total.

    Each scalar stays under max_scalar_bytes and the node count stays far under
    max_nodes, so max_owned_bytes is the only limit an input can cross.
    """
    name = "t" * 200
    base = weight(SEQ([T(name, S("")) for _ in range(8)]))
    spare = target - base
    lengths = [spare // 8 + (1 if i < spare % 8 else 0) for i in range(8)]
    contents = ["x" * n for n in lengths]
    value = SEQ([T(name, S(c)) for c in contents])
    text = "[" + ", ".join("!%s %s" % (name, c) for c in contents) + "]\n"
    return text, value, weight(value)


def gen_limits(limits):
    yield from limit_rows("max_nodes", limits["max_nodes"], by_nodes)
    yield from limit_rows("max_owned_bytes", limits["max_owned_bytes"], by_weight)


def generate(parameters):
    if parameters["set"] == "values":
        rows = gen_values()
    else:
        rows = gen_limits({"max_nodes": parameters["max_nodes"], "max_owned_bytes": parameters["max_owned_bytes"]})
    for local_id, text, expectation in rows:
        yield local_id, "tags", text, expectation, []
