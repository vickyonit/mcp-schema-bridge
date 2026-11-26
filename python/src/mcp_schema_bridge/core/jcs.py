"""RFC 8785 JSON Canonicalization Scheme (JCS).

Used for golden files, hashes, and description-hint values, so output is byte-identical
across platforms and (from v0.2) across the Python and TypeScript implementations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

MAX_SAFE_INTEGER = 2**53 - 1

_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def canonicalize(value: Any) -> str:
    """Return the RFC 8785 canonical JSON text for ``value``."""
    parts: list[str] = []
    _write(value, parts)
    return "".join(parts)


def canonicalize_bytes(value: Any) -> bytes:
    return canonicalize(value).encode("utf-8")


def _write(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        out.append(format_integer(value))
    elif isinstance(value, float):
        out.append(format_number(value))
    elif isinstance(value, str):
        out.append(quote_string(value))
    elif isinstance(value, Mapping):
        _write_object(cast(Mapping[Any, Any], value), out)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        out.append("[")
        for i, item in enumerate(cast(Sequence[Any], value)):
            if i:
                out.append(",")
            _write(item, out)
        out.append("]")
    else:
        raise TypeError(f"not JSON-serializable: {type(value).__name__}")


def _write_object(obj: Mapping[Any, Any], out: list[str]) -> None:
    for key in obj:
        if not isinstance(key, str):
            raise TypeError(f"object keys must be strings, got {type(key).__name__}")
    out.append("{")
    for i, key in enumerate(sorted(obj, key=utf16_sort_key)):
        if i:
            out.append(",")
        out.append(quote_string(key))
        out.append(":")
        _write(obj[key], out)
    out.append("}")


def utf16_sort_key(s: str) -> bytes:
    """Sort key ordering strings by UTF-16 code units, as RFC 8785 §3.2.3 requires."""
    return s.encode("utf-16-be", "surrogatepass")


def quote_string(s: str) -> str:
    buf = ['"']
    for ch in s:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise ValueError("lone surrogate code point in string is not valid I-JSON")
        esc = _SHORT_ESCAPES.get(cp)
        if esc is not None:
            buf.append(esc)
        elif cp < 0x20:
            buf.append(f"\\u{cp:04x}")
        else:
            buf.append(ch)
    buf.append('"')
    return "".join(buf)


def format_integer(n: int) -> str:
    if abs(n) > MAX_SAFE_INTEGER:
        raise ValueError(f"integer {n} is outside the I-JSON safe range (|n| <= 2**53 - 1)")
    return str(n)


def format_number(x: float) -> str:
    """Format a float exactly like ECMAScript ``Number.prototype.toString``."""
    if not math.isfinite(x):
        raise ValueError("JSON numbers must be finite (NaN/Infinity are not allowed)")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    digits, n = _shortest_digits(abs(x))
    k = len(digits)
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        exp = f"e{'+' if e >= 0 else '-'}{abs(e)}"
        body = (digits if k == 1 else digits[0] + "." + digits[1:]) + exp
    return sign + body


def _shortest_digits(x: float) -> tuple[str, int]:
    """Return (digits, n) with x == 0.<digits> * 10**n, using the shortest round-trip digits."""
    mantissa, _, exponent = repr(x).partition("e")
    int_part, _, frac_part = mantissa.partition(".")
    if frac_part == "0":
        frac_part = ""
    all_digits = int_part + frac_part
    stripped = all_digits.lstrip("0")
    leading_zeros = len(all_digits) - len(stripped)
    n = len(int_part) - leading_zeros + (int(exponent) if exponent else 0)
    return stripped.rstrip("0") or "0", n
