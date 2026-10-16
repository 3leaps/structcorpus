"""Event notations for the events expectation layer (DDR-0010), Python 3.9+ stdlib.

Two notations share one event grammar and differ only in how values are escaped:

  yaml-test-suite         values escape \\ NUL BS TAB LF CR; other characters are raw
  structcorpus-events/1   values also escape every other control, DEL, C1, U+2028, U+2029

An event string is parsed into fields first and only its value is unescaped, so a
backslash in an anchor, alias, or tag is never read as an escape.
"""

import re

YTS = "yaml-test-suite"
SCE1 = "structcorpus-events/1"
NOTATIONS = (YTS, SCE1)

KINDS = ("+STR", "-STR", "+DOC", "-DOC", "+MAP", "-MAP", "+SEQ", "-SEQ", "=VAL", "=ALI")
STYLES = (":", "'", '"', "|", ">")

YTS_SHORT = {"\\": "\\\\", "\x00": "\\0", "\x08": "\\b", "\x09": "\\t", "\x0a": "\\n", "\x0d": "\\r"}
SHORT_DECODE = {"\\": "\\", "0": "\x00", "b": "\x08", "t": "\x09", "n": "\x0a", "r": "\x0d"}
SEPARATORS = {"\u2028": "\\u2028", "\u2029": "\\u2029"}


class NotationError(ValueError):
    pass


def _hex_escaped(ch):
    """Characters written as \\xHH in structcorpus-events/1."""
    o = ord(ch)
    return ch not in YTS_SHORT and (o <= 0x1F or 0x7F <= o <= 0x9F)


def _needs_escape(ch):
    return ch in YTS_SHORT or _hex_escaped(ch) or ch in SEPARATORS


def encode_value(text, notation):
    if notation not in NOTATIONS:
        raise NotationError("unknown notation %r" % notation)
    out = []
    for ch in text:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            raise NotationError("a value cannot contain a surrogate code point")
        if ch in YTS_SHORT:
            out.append(YTS_SHORT[ch])
        elif notation == SCE1 and _hex_escaped(ch):
            out.append("\\x%02X" % ord(ch))
        elif notation == SCE1 and ch in SEPARATORS:
            out.append(SEPARATORS[ch])
        else:
            out.append(ch)
    return "".join(out)


def decode_value(text, notation):
    if notation not in NOTATIONS:
        raise NotationError("unknown notation %r" % notation)
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "\\":
            if 0xD800 <= ord(ch) <= 0xDFFF:
                raise NotationError("surrogate code point in value")
            if ch in YTS_SHORT or (notation == SCE1 and _needs_escape(ch)):
                raise NotationError("raw U+%04X must be escaped" % ord(ch))
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(text):
            raise NotationError("value ends inside an escape")
        e = text[i + 1]
        if e in SHORT_DECODE:
            out.append(SHORT_DECODE[e])
            i += 2
        elif notation == SCE1 and e == "x":
            digits = text[i + 2 : i + 4]
            if not re.fullmatch(r"[0-9A-F]{2}", digits):
                raise NotationError("\\x needs exactly two uppercase hex digits")
            ch = chr(int(digits, 16))
            if not _hex_escaped(ch):
                raise NotationError("\\x%s is not the canonical spelling of U+%04X" % (digits, ord(ch)))
            out.append(ch)
            i += 4
        elif notation == SCE1 and e == "u":
            esc = text[i : i + 6]
            hit = [c for c, s in SEPARATORS.items() if s == esc]
            if not hit:
                raise NotationError("\\u is only for \\u2028 and \\u2029")
            out.append(hit[0])
            i += 6
        else:
            raise NotationError("unknown escape %r" % ("\\" + e))
    return "".join(out)


# YAML 1.2.2 ns-anchor-char: ns-char minus the flow indicators. Of the C1 range,
# only NEL is c-printable; DEL, the other C1 controls, surrogates and BOM are not names.
ANCHOR_RE = re.compile(r"[^ \t\r\n\[\]{},\x00-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff\ufeff\ufffe\uffff]+\Z")


def _raw_control(ch):
    return ord(ch) <= 0x1F or 0x7F <= ord(ch) <= 0x9F or ch in SEPARATORS


def _check_name(name, notation, what):
    if not name or not ANCHOR_RE.match(name):
        raise NotationError("%s %r is not a YAML anchor name" % (what, name))
    if notation == SCE1 and any(_raw_control(c) for c in name):
        raise NotationError("%s %r is outside the structcorpus-events/1 domain" % (what, name))


def _check_tag(tag, notation):
    if not tag or ">" in tag or any(_raw_control(c) or 0xD800 <= ord(c) <= 0xDFFF for c in tag):
        raise NotationError("tag %r cannot be written between < and >" % tag)


def parse(event, notation):
    """Parse one event string into a dict of fields, decoding only the value."""
    if notation not in NOTATIONS:
        raise NotationError("unknown notation %r" % notation)
    kind, rest = event[:4], event[4:]
    if kind not in KINDS:
        raise NotationError("unknown event kind %r" % kind)
    f = {"kind": kind}
    if kind in ("+STR", "-STR", "-MAP", "-SEQ"):
        if rest:
            raise NotationError("%s takes no fields" % kind)
        return f
    if kind in ("+DOC", "-DOC"):
        marker = " ---" if kind == "+DOC" else " ..."
        if rest not in ("", marker):
            raise NotationError("bad %s fields %r" % (kind, rest))
        f["explicit"] = rest == marker
        return f
    if kind == "=ALI":
        if not rest.startswith(" *"):
            raise NotationError("=ALI needs ' *<alias>'")
        f["alias"] = rest[2:]
        _check_name(f["alias"], notation, "alias")
        return f
    if kind in ("+MAP", "+SEQ"):
        flow = " {}" if kind == "+MAP" else " []"
        if rest.startswith(flow):
            f["flow"] = True
            rest = rest[3:]
    if rest.startswith(" &"):
        end = rest.find(" ", 2)
        end = len(rest) if end < 0 else end
        f["anchor"] = rest[2:end]
        _check_name(f["anchor"], notation, "anchor")
        rest = rest[end:]
    if rest.startswith(" <"):
        end = rest.find(">", 2)
        if end < 0:
            raise NotationError("unterminated tag")
        f["tag"] = rest[2:end]
        _check_tag(f["tag"], notation)
        rest = rest[end + 1 :]
    if kind == "=VAL":
        if len(rest) < 2 or rest[0] != " " or rest[1] not in STYLES:
            raise NotationError("=VAL needs a style marker")
        f["style"] = rest[1]
        f["value"] = decode_value(rest[2:], notation)
    elif rest:
        raise NotationError("unexpected text %r in %s" % (rest, kind))
    return f


def render(fields, notation):
    """Write fields as one event string in notation; fails if a field is outside its domain."""
    if notation not in NOTATIONS:
        raise NotationError("unknown notation %r" % notation)
    kind = fields.get("kind")
    allowed = {"kind"}
    required = {"kind"}
    if kind not in KINDS:
        raise NotationError("unknown event kind %r" % kind)
    if kind in ("+DOC", "-DOC"):
        allowed.add("explicit")
    if kind in ("+MAP", "+SEQ", "=VAL"):
        allowed.update(("anchor", "tag"))
    if kind in ("+MAP", "+SEQ"):
        allowed.add("flow")
    if kind == "=ALI":
        allowed.add("alias")
        required.add("alias")
    if kind == "=VAL":
        allowed.update(("style", "value"))
        required.update(("style", "value"))
    if set(fields) - allowed or required - set(fields):
        raise NotationError("invalid fields for %s" % kind)
    for name in allowed - {"kind"}:
        if name in fields and not isinstance(fields[name], bool if name in ("explicit", "flow") else str):
            raise NotationError("invalid type for %s" % name)
    if kind == "=VAL" and fields["style"] not in STYLES:
        raise NotationError("invalid scalar style %r" % fields["style"])
    out = [kind]
    if kind in ("+DOC", "-DOC") and fields.get("explicit"):
        out.append(" ---" if kind == "+DOC" else " ...")
    if kind == "=ALI":
        _check_name(fields["alias"], notation, "alias")
        out.append(" *" + fields["alias"])
    if kind in ("+MAP", "+SEQ") and fields.get("flow"):
        out.append(" {}" if kind == "+MAP" else " []")
    if "anchor" in fields:
        _check_name(fields["anchor"], notation, "anchor")
        out.append(" &" + fields["anchor"])
    if "tag" in fields:
        _check_tag(fields["tag"], notation)
        out.append(" <%s>" % fields["tag"])
    if kind == "=VAL":
        out.append(" " + fields["style"] + encode_value(fields["value"], notation))
    return "".join(out)


def convert(event, source, target):
    return render(parse(event, source), target)


def needs_sce1(fields_list):
    """Whether a new record should use structcorpus-events/1 (DDR-0010 item 7)."""
    fields_list = list(fields_list)
    for fields in fields_list:
        render(fields, YTS)  # An event outside both domains has no automatic fallback.
    needed = any(any(_hex_escaped(c) or c in SEPARATORS for c in f.get("value", "")) for f in fields_list)
    if needed:
        try:
            for fields in fields_list:
                render(fields, SCE1)
        except NotationError:
            return False
    return needed


def display(event):
    """An escaped rendering for diagnostics: never writes a raw control to a terminal."""
    out = []
    for ch in event:
        o = ord(ch)
        if (
            o <= 0x1F
            or 0x7F <= o <= 0x9F
            or ch in SEPARATORS
            or 0xD800 <= o <= 0xDFFF
            or ch
            in "\u061c\u200b\u200c\u200d\u200e\u200f\u2060\u2066\u2067\u2068\u2069\u202a\u202b\u202c\u202d\u202e\ufeff"
        ):
            out.append("\\u{%04X}" % o)
        else:
            out.append(ch)
    return "".join(out)
