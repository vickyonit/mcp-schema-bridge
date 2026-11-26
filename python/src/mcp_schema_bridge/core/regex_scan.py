"""Purely syntactic scanner for ECMA-262 regular-expression features (never compiles patterns).

Detected features: backreference, lookaround, word_boundary, large_quantifier, unicode_property,
inline_flags. Shared test vectors: spec/regex-vectors.json.
"""

from __future__ import annotations

LARGE_QUANTIFIER_THRESHOLD = 100


def scan(pattern: str) -> set[str]:
    found: set[str] = set()
    i, n = 0, len(pattern)
    in_class = False
    while i < n:
        c = pattern[i]
        if c == "\\" and i + 1 < n:
            nxt = pattern[i + 1]
            if not in_class:
                named_ref = nxt == "k" and i + 2 < n and pattern[i + 2] == "<"
                if nxt in "123456789" or named_ref:
                    found.add("backreference")
                elif nxt in "bB":
                    found.add("word_boundary")
            if nxt in "pP" and i + 2 < n and pattern[i + 2] == "{":
                found.add("unicode_property")
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            continue
        if c == "(" and i + 1 < n and pattern[i + 1] == "?":
            rest = pattern[i + 2 : i + 4]
            if rest[:1] in ("=", "!") or rest in ("<=", "<!"):
                found.add("lookaround")
            elif rest[:1] not in (":", "<") and rest[:1] != "":
                # (?i) (?i:...) (?-i) ... inline modifiers
                found.add("inline_flags")
            i += 2
            continue
        if c == "{":
            end = pattern.find("}", i)
            if end != -1:
                body = pattern[i + 1 : end]
                parts = body.split(",")
                if (
                    1 <= len(parts) <= 2
                    and parts[0].isdigit()
                    and all(p == "" or p.isdigit() for p in parts[1:])
                ):
                    bounds = [int(p) for p in parts if p]
                    if any(b > LARGE_QUANTIFIER_THRESHOLD for b in bounds):
                        found.add("large_quantifier")
                    i = end + 1
                    continue
        i += 1
    return found
