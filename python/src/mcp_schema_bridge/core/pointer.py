"""RFC 6901 JSON Pointer helpers."""

from __future__ import annotations

from urllib.parse import unquote


def escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def join(base: str, *tokens: str | int) -> str:
    return base + "".join("/" + escape_token(str(t)) for t in tokens)


def split(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"JSON Pointer must start with '/': {pointer!r}")
    return [unescape_token(t) for t in pointer[1:].split("/")]


def decode_fragment(fragment: str) -> list[str]:
    """Decode a URI fragment JSON Pointer (``#/a/b``): percent-decoding first, then ~1, then ~0."""
    frag = fragment[1:] if fragment.startswith("#") else fragment
    return split(unquote(frag, errors="strict"))
