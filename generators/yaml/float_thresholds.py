"""Exact binary64 and binary32 rounding thresholds (Python 3.9+ stdlib).

Expected values are derived from the published yamlprims specification
revision 1.1, sections 4.1 and 8, independently of any implementation:
https://github.com/3leaps/yamlprims/blob/spec-v1.1/docs/spec/yamlprims-spec.md

A plain float literal resolves to the correctly rounded binary64 value, ties to
even; a finite literal that rounds to infinity is float_out_of_range (4.1). The
f32 target converts that binary64 Float to binary32, again to nearest with ties
to even (8). The f32 result is therefore rounded twice, and rows just beside a
binary32 midpoint show where that differs from rounding the text directly.

Every input is an exact decimal rendering of a rational chosen beside a
rounding boundary: an exact midpoint between adjacent values (the tie rule
decides), and points just above and below it, in both signs. Bits are computed
here with fractions.Fraction; nothing calls float(), so the tests can check the
rows against the host's own correctly rounded conversion.

Each yielded case is (local_id, category, yaml_text, expectation, typed).
"""

from fractions import Fraction


class Format:
    def __init__(self, name, precision, emin, emax, width):
        self.name = name
        self.p = precision  # significand bits, including the implicit bit
        self.emin = emin
        self.emax = emax
        self.width = width  # total bits
        self.bias = emax

    def round(self, q):
        """Round a nonzero-or-zero Fraction to nearest, ties to even.

        Returns (sign, n, e) with value n * 2**(e - p + 1), or None on overflow.
        n < 2**(p-1) only for subnormals (e == emin) and zero.
        """
        sign = 1 if q < 0 else 0
        a = -q if sign else q
        if a == 0:
            return sign, 0, self.emin
        e = a.numerator.bit_length() - a.denominator.bit_length()
        if Fraction(2) ** e > a:
            e -= 1
        # now 2**e <= a < 2**(e+1)
        e = max(e, self.emin)
        m = a / Fraction(2) ** (e - self.p + 1)
        n = m.numerator // m.denominator
        rem = m - n
        if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and n % 2 == 1):
            n += 1
        if n == 2**self.p:
            n //= 2
            e += 1
        if e > self.emax:
            return None
        return sign, n, e

    def value(self, rounded):
        sign, n, e = rounded
        v = Fraction(n) * Fraction(2) ** (e - self.p + 1)
        return -v if sign else v

    def bits(self, rounded):
        sign, n, e = rounded
        if n < 2 ** (self.p - 1):
            biased, frac = 0, n
        else:
            biased, frac = e + self.bias, n - 2 ** (self.p - 1)
        word = (sign << (self.width - 1)) | (biased << (self.p - 1)) | frac
        return "%0*x" % (self.width // 4, word)

    def ulp(self, e):
        return Fraction(2) ** (e - self.p + 1)


F64 = Format("binary64", 53, -1022, 1023, 64)
F32 = Format("binary32", 24, -126, 127, 32)


def decimal_text(q, style="auto"):
    """Exact decimal spelling of a dyadic or decimal Fraction (no rounding)."""
    sign = "-" if q < 0 else ""
    a = -q if q < 0 else q
    den = a.denominator
    k = 0
    while den % 2 == 0 or den % 5 == 0:
        den //= 2 if den % 2 == 0 else 5
        k += 1
    if den != 1:
        raise ValueError("not a terminating decimal: %r" % q)
    # a == digits / 10**k exactly
    digits = a.numerator * (10**k // a.denominator)
    s = str(digits)
    fixed_int = s[:-k] if k and len(s) > k else ("0" if k else s)
    fixed_frac = (s[-k:] if len(s) >= k else "0" * (k - len(s)) + s) if k else ""
    fixed = sign + fixed_int + "." + (fixed_frac or "0")
    if style == "fixed" or (style == "auto" and len(fixed) <= 64):
        return fixed
    # scientific: d.ddd e(exp), exact
    exp = len(s) - 1 - k
    stripped = s.rstrip("0") or "0"
    mant = stripped[0] + "." + (stripped[1:] or "0")
    return "%s%se%d" % (sign, mant, exp)


def neighbours(fmt, x):
    """The representable value x (positive) and the next one up."""
    r = fmt.round(x)
    assert fmt.value(r) == x, "anchor must be representable"
    _sign, n, e = r
    return x, x + fmt.ulp(e)


def eps_below(q, gap):
    """A decimal step strictly smaller than any binary64 rounding gap near q."""
    k = 0
    while Fraction(1, 10**k) >= gap:
        k += 1
    return Fraction(1, 10 ** (k + 1))


# Anchors: (name, format, lower representable value). The midpoint is between
# the anchor and the next representable value up.
TWO = Fraction(2)
F64_MAX = (TWO - TWO**-52) * TWO**1023
F32_MAX = (TWO - TWO**-23) * TWO**127
F64_ANCHORS = [
    ("one", Fraction(1)),
    ("one-odd", 1 + TWO**-52),  # the tie goes up to the even neighbour
    ("int-2p53", TWO**53),
    ("tenth", None),  # the binary64 neighbours of 0.1, found by rounding
    ("max", F64_MAX),
    ("min-subnormal", Fraction(0)),
    ("min-subnormal-odd", TWO**-1074),
    ("subnormal-top", (TWO**52 - 1) * TWO**-1074),
    ("min-normal", TWO**-1022),
]
F32_ANCHORS = [
    ("one", Fraction(1)),
    ("one-odd", 1 + TWO**-23),
    ("max", F32_MAX),
    ("min-subnormal", Fraction(0)),
    ("subnormal-top", (TWO**23 - 1) * TWO**-149),
]


def _f64_anchor(name, lo):
    if lo is None:  # largest binary64 value not above 0.1
        r = F64.round(Fraction(1, 10))
        v = F64.value(r)
        if v > Fraction(1, 10):
            v -= F64.ulp(r[2])
        lo = v
    if lo == 0:
        return lo, TWO**-1074
    return neighbours(F64, lo)


def _f32_anchor(lo):
    if lo == 0:
        return lo, TWO**-149
    return neighbours(F32, lo)


def _expect(q):
    """The resolved value (4.1) and the rounded binary64 triple, or an error."""
    r = F64.round(q)
    if r is None:
        return {"error": {"phase": "resolution", "kind": "float_out_of_range"}}, None
    return {"documents": [_k({"t": "float", "bits": F64.bits(r)})]}, r


def _k(v):
    return {"t": "map", "entries": [[{"t": "str", "v": "k"}, v]]}


def _typed(r64, failure):
    """f64 and f32 typed entries (8) for the value at path ["k"].

    f32 rounds the binary64 value again. The sign comes from the binary64
    triple, so a negative value that rounded to -0.0 stays negative.
    """
    out = []
    for target in ("f64", "f32"):
        entry = {"path": ["k"], "target": target}
        if failure is not None:
            entry["error"] = failure
        elif target == "f64":
            entry["result"] = {"t": "float", "bits": F64.bits(r64)}
        else:
            sign = r64[0]
            r32 = F32.round(abs(F64.value(r64)))
            if r32 is None:
                entry["error"] = {"phase": "typed", "kind": "float_out_of_range"}
            else:
                entry["result"] = {"t": "float32", "bits": F32.bits((sign,) + r32[1:])}
        out.append(entry)
    return out


def _around(mid, gap):
    """The midpoint, and exact decimals just below and above it (closer than gap)."""
    tiny = eps_below(mid, gap)
    return [("mid", mid), ("below", mid - tiny), ("above", mid + tiny)]


def rows():
    """(name, rational) pairs in a fixed order, all positive."""
    out = []
    for name, lo in F64_ANCHORS:
        lo, hi = _f64_anchor(name, lo)
        for label, q in _around((lo + hi) / 2, hi - lo):
            out.append(("f64-%s-%s" % (name, label), q))
    for name, lo in F32_ANCHORS:
        lo, hi = _f32_anchor(lo)
        mid = (lo + hi) / 2  # exactly representable in binary64
        # Closer than one binary64 step: the text rounds to the binary32
        # midpoint in binary64, so the f32 tie rule decides (double rounding).
        f64_gap = F64.ulp(F64.round(mid)[2])
        points = _around(mid, f64_gap)
        # A quarter step away: both roundings agree.
        quarter = (hi - lo) / 4
        points += [("below-q", mid - quarter), ("above-q", mid + quarter)]
        for label, q in points:
            out.append(("f32-%s-%s" % (name, label), q))
    out.append(("f64-1e23", Fraction(10) ** 23))  # between two binary64 values
    return out


def spellings(q):
    """Other spellings of the same positive value: sign, exponent, zero padding."""
    fixed = decimal_text(q, style="fixed")
    return ["+" + fixed, decimal_text(q, style="scientific").replace("e", "E"), "00" + fixed + "00"]


def generate(parameters):
    """Yield every row in both signs; the rows near 1 also in other spellings."""
    if parameters.get("set") != "thresholds":
        raise ValueError("unknown set %r" % parameters.get("set"))
    n = 0
    for name, q in rows():
        texts = [decimal_text(q), decimal_text(-q)]
        if name.startswith(("f64-one-", "f32-one-")):
            texts += spellings(q)
        for text in texts:
            n += 1
            value = -q if text.startswith("-") else q
            expectation, r64 = _expect(value)
            typed = _typed(r64, expectation.get("error"))
            yield ("t%03d" % n, "numeric-resolution", "k: %s\n" % text, expectation, typed)
