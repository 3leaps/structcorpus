"""Specification 1.4 boundary recipes (Python 3.9+ stdlib).

Expected results follow the published yamlprims specification revision 1.4,
sections 5.2, 5.4, 6, and 7.1:
https://github.com/3leaps/yamlprims/blob/spec-v1.4/docs/spec/yamlprims-spec.md

Sets (the recipe's "set" parameter):
  depth    S_n(0) for n = 127, 128, 129 and alias insertion for k = 125, 126, 127,
           at max_depth 128. S_n is n opening brackets, 0, n closing brackets,
           and one LF. The alias input is ``{a: &a [], b:`` plus S_k(*a) plus
           ``}`` and one LF.
  depth255 the same constructions at the configured ceiling: n = 254, 255, 256
           and k = 252, 253, 254, with max_depth 255.
  entries  ordinary mapping admission at max_mapping_entries 2. Two distinct
           keys succeed. A repeated second key is duplicate_key. A third key
           is max_mapping_entries, whether or not that key repeats. A NaN key
           is invalid_key at key completion, before capacity and before the value.

Accounting is an independent model of those sections. It is not a YAML parser.
Each yielded case is (local_id, category, yaml_text, expectation, typed).
"""

LIMIT_FIELDS = (
    "max_input_bytes",
    "max_depth",
    "max_nodes",
    "max_expanded_nodes",
    "max_alias_events",
    "max_owned_bytes",
    "max_scalar_bytes",
    "max_key_bytes",
    "max_mapping_entries",
    "max_documents",
    "max_output_bytes",
    "max_warnings",
)

# Compared against a profile while a document is loaded. Output and warning
# limits belong to encoding and lint, not to these load rows.
LOAD_FIELDS = (
    "max_input_bytes",
    "max_depth",
    "max_nodes",
    "max_expanded_nodes",
    "max_alias_events",
    "max_owned_bytes",
    "max_scalar_bytes",
    "max_key_bytes",
    "max_mapping_entries",
    "max_documents",
)


def S(v):
    return {"t": "str", "v": v}


def INT(n):
    return {"t": "int", "v": str(n)}


def SEQ(items):
    return {"t": "seq", "items": list(items)}


def MAP(pairs):
    return {"t": "map", "entries": [[k, v] for k, v in pairs]}


def node_count(v):
    if v["t"] == "seq":
        return 1 + sum(node_count(i) for i in v["items"])
    if v["t"] == "map":
        return 1 + sum(node_count(k) + node_count(x) for k, x in v["entries"])
    return 1


def logical_weight(v):
    """Section 6 subtree weight. String text counts; Int text does not."""
    if v["t"] == "str":
        return 64 + len(v["v"].encode("utf-8"))
    if v["t"] == "seq":
        return 64 + sum(logical_weight(i) for i in v["items"])
    if v["t"] == "map":
        children = sum(logical_weight(k) + logical_weight(x) for k, x in v["entries"])
        return 64 + 24 * len(v["entries"]) + children
    return 64


def limits_from(parameters):
    missing = [name for name in LIMIT_FIELDS if "limit_" + name not in parameters]
    if missing:
        raise ValueError("missing limit parameters: %s" % ", ".join(missing))
    return {name: parameters["limit_" + name] for name in LIMIT_FIELDS}


def load_measures(text, depth, nodes, owned, expanded, aliases, entries, scalar, key):
    return {
        "max_input_bytes": len(text.encode("utf-8")),
        "max_depth": depth,
        "max_nodes": nodes,
        "max_expanded_nodes": expanded,
        "max_alias_events": aliases,
        "max_owned_bytes": owned,
        "max_scalar_bytes": scalar,
        "max_key_bytes": key,
        "max_mapping_entries": entries,
        "max_documents": 1,
    }


def exceeded(limits, measures):
    return [name for name in LOAD_FIELDS if measures[name] > limits[name]]


def require_only(limits, measures, winner, row):
    over = exceeded(limits, measures)
    expect = [] if winner is None else [winner]
    if over != expect:
        raise ValueError("%s: limits crossed %s, expected %s, measures %s" % (row, over, expect, measures))


def limit_exceeded(name, configured):
    return {"error": {"phase": "limit", "kind": "limit_exceeded", "limit": name, "configured": configured}}


def seq_text(n):
    """S_n(0): n brackets around the scalar 0, then one LF."""
    text = ("[" * n) + "0" + ("]" * n) + "\n"
    value = INT(0)
    for _ in range(n):
        value = SEQ([value])
    return text, value


def alias_text(k):
    """``{a: &a [], b: S_k(*a)}`` plus one LF. The anchor is an empty sequence, H = 1."""
    text = "{a: &a [], b: " + ("[" * k) + "*a" + ("]" * k) + "}\n"
    copied = SEQ([])
    nested = copied
    for _ in range(k):
        nested = SEQ([nested])
    value = MAP([(S("a"), SEQ([])), (S("b"), nested)])
    return text, value


def alias_levels(k):
    """Source-collection maximum and alias insertion level for k >= 1.

    The k-th bracket of the alias value consumes level k + 1. The alias is
    placed at p = k + 1 with H(anchor) = 1, so the check is k + 2.
    """
    if k < 1:
        raise ValueError(k)
    return (k + 1, k + 2)


def gen_depth_rows(limits, depths, aliases):
    for n in depths:
        text, value = seq_text(n)
        measures = load_measures(
            text,
            depth=n,
            nodes=node_count(value),
            owned=logical_weight(value),
            expanded=0,
            aliases=0,
            entries=0,
            scalar=1,
            key=0,
        )
        row = "depth-%d" % n
        if n > limits["max_depth"]:
            require_only(limits, measures, "max_depth", row)
            expectation = limit_exceeded("max_depth", limits["max_depth"])
        else:
            require_only(limits, measures, None, row)
            expectation = {"documents": [value]}
        yield row, text, expectation

    for k in aliases:
        text, value = alias_text(k)
        source_max, insertion = alias_levels(k)
        if source_max > limits["max_depth"]:
            raise ValueError(
                "alias-%d: source level %d exceeds %d before alias placement" % (k, source_max, limits["max_depth"])
            )
        # Registration of the anchored empty sequence adds its 64-byte weight
        # and no node. The copy is included so a row that only fails placement
        # still fits every other budget even if the copy were counted.
        measures = load_measures(
            text,
            depth=insertion,
            nodes=node_count(value),
            owned=logical_weight(value) + 64,
            expanded=node_count(SEQ([])),
            aliases=1,
            entries=2,
            scalar=1,
            key=logical_weight(S("a")),
        )
        row = "alias-%d" % k
        if insertion > limits["max_depth"]:
            require_only(limits, measures, "max_depth", row)
            expectation = limit_exceeded("max_depth", limits["max_depth"])
        else:
            require_only(limits, measures, None, row)
            expectation = {"documents": [value]}
        yield row, text, expectation


def gen_depth(limits):
    return gen_depth_rows(limits, (127, 128, 129), (125, 126, 127))


def gen_depth255(limits):
    """Section 6 ceiling: levels 254/255/256 at configured max_depth 255."""
    if limits["max_depth"] != 255:
        raise ValueError("depth255 rows require max_depth 255, got %s" % limits["max_depth"])
    return gen_depth_rows(limits, (254, 255, 256), (252, 253, 254))


def flow_pairs(pairs):
    return "{" + ", ".join("%s: %s" % (k, v) for k, v in pairs) + "}\n"


def gen_entries(limits):
    specs = (
        ("entries-two", (("a", "0"), ("b", "0"))),
        ("entries-duplicate", (("a", "0"), ("a", "1"))),
        ("entries-third-duplicate", (("a", "0"), ("b", "0"), ("a", "1"))),
        ("entries-third-new", (("a", "0"), ("b", "0"), ("c", "1"))),
    )
    for row, pairs in specs:
        text = flow_pairs(pairs)
        nodes = 1
        owned = 64
        max_key = 0
        max_scalar = 0
        seen = []
        outcome = "ok"
        admitted = 0
        for k, v in pairs:
            if not v.isdigit():
                raise ValueError("%s: value %r is not an integer token" % (row, v))
            key_w = logical_weight(S(k))
            nodes += 2
            owned += key_w + 64 + 24
            max_key = max(max_key, key_w)
            max_scalar = max(max_scalar, len(k.encode("utf-8")), len(v.encode("utf-8")))
            admitted += 1
            if admitted > limits["max_mapping_entries"]:
                outcome = "capacity"
                break
            if k in seen:
                outcome = "duplicate"
                break
            seen.append(k)
        would = MAP([(S(k), INT(int(v))) for k, v in pairs])
        if node_count(would) != nodes or logical_weight(would) != owned:
            raise ValueError("%s: entry weight diverged from the node model" % row)
        measures = load_measures(
            text,
            depth=1,
            nodes=nodes,
            owned=owned,
            expanded=0,
            aliases=0,
            entries=admitted,
            scalar=max_scalar,
            key=max_key,
        )
        if outcome == "ok":
            require_only(limits, measures, None, row)
            expectation = {"documents": [would]}
        elif outcome == "capacity":
            require_only(limits, measures, "max_mapping_entries", row)
            expectation = limit_exceeded("max_mapping_entries", limits["max_mapping_entries"])
        elif outcome == "duplicate":
            require_only(limits, measures, None, row)
            expectation = {"error": {"phase": "structure", "kind": "duplicate_key"}}
        else:
            raise ValueError(outcome)
        yield row, text, expectation
    for row in gen_nan_keys(limits):
        yield row


def gen_nan_keys(limits):
    """Section 5.2: a NaN key fails when the key is completed.

    The value is not built, and the 24-byte entry overhead is not charged.
    Capacity is not consulted. A Float key weighs 64, with no scalar text.
    """
    prefix_owned = 64 + 2 * (logical_weight(S("a")) + 64 + 24)
    rows = (
        ("entries-nan-at-cap", "{a: 0, b: 0, .nan: 1}\n", 6, prefix_owned + 64, 2, logical_weight(S("a")), 1),
        ("entries-nan-before-value", "{.nan: !!int nope}\n", 2, 128, 0, 64, 0),
    )
    for row, text, nodes, owned, admitted, key_w, scalar in rows:
        if 64 > limits["max_key_bytes"]:
            raise ValueError("%s: NaN key weight exceeds max_key_bytes before invalid_key" % row)
        measures = load_measures(
            text,
            depth=1,
            nodes=nodes,
            owned=owned,
            expanded=0,
            aliases=0,
            entries=admitted,
            scalar=scalar,
            key=key_w,
        )
        require_only(limits, measures, None, row)
        yield row, text, {"error": {"phase": "structure", "kind": "invalid_key"}}


def generate(parameters):
    limits = limits_from(parameters)
    kind = parameters["set"]
    if kind == "depth":
        rows = gen_depth(limits)
    elif kind == "depth255":
        rows = gen_depth255(limits)
    elif kind == "entries":
        rows = gen_entries(limits)
    else:
        raise ValueError("unknown set %r" % kind)
    for local_id, text, expectation in rows:
        yield local_id, "resource-limits", text, expectation, []
