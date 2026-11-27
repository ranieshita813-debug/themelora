"""Parsing of shellcode text, bad-byte lists, base addresses, and on/off switches."""

from __future__ import annotations

import base64
import binascii
import re
from typing import List, Optional

from malora.constants import MAX_BASE, OFF_WORDS, ON_WORDS, PAGE_SIZE
from malora.errors import MaloraError

FORMATS = ("hex", "c", "base64", "raw")

_HEX_DIGITS = re.compile(r"[0-9a-fA-F]+")
_C_ESCAPE = re.compile(r"\\x([0-9a-fA-F]{2})", re.IGNORECASE)
_HEX_PREFIX = re.compile(r"\\x|0[xX]")
_SEPARATORS = re.compile(r"[\s,;:_]+")


def parse_shellcode(text: str, fmt: str) -> bytes:
    """Convert shellcode text in the given format into bytes."""
    if fmt == "raw":
        try:
            return text.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise MaloraError(f"raw input has characters outside one byte: {exc}") from None

    if fmt == "c":
        matches = _C_ESCAPE.findall(text)
        if not matches:
            raise MaloraError("no \\xNN escapes found in C-style input")
        return bytes(int(m, 16) for m in matches)

    if fmt == "base64":
        cleaned = re.sub(r"\s+", "", text)
        try:
            return base64.b64decode(cleaned, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MaloraError(f"invalid base64: {exc}") from None

    if fmt == "hex":
        cleaned = _SEPARATORS.sub("", _HEX_PREFIX.sub("", text))
        if not cleaned:
            raise MaloraError("empty hex input")
        bad = re.search(r"[^0-9a-fA-F]", cleaned)
        if bad:
            raise MaloraError(f"invalid hex character {bad.group()!r}")
        if len(cleaned) % 2:
            # Padding would silently shift every byte, so refuse instead.
            raise MaloraError(
                f"odd number of hex digits ({len(cleaned)}); a byte is missing"
            )
        return bytes.fromhex(cleaned)

    raise MaloraError(f"unknown format '{fmt}'")


def auto_detect_format(text: str) -> str:
    """Guess the input format.

    Any hex-only string is read as hex, which means base64 such as "AAAA" is
    ambiguous. Pass an explicit format to resolve that.
    """
    stripped = text.strip()
    if _C_ESCAPE.search(stripped):
        return "c"
    compact = _SEPARATORS.sub("", _HEX_PREFIX.sub("", stripped))
    if compact and _HEX_DIGITS.fullmatch(compact):
        return "hex"
    return "base64"


def parse_badchars(text: str) -> List[int]:
    """Parse '00,0a,0d', '\\x00\\x0a', or '0x00 0x0a' into sorted byte values."""
    spaced = _HEX_PREFIX.sub(" ", text)
    tokens = [t for t in _SEPARATORS.split(spaced.strip()) if t]
    values = set()
    for token in tokens:
        if not re.fullmatch(r"[0-9a-fA-F]{1,2}", token):
            raise MaloraError(f"invalid bad byte '{token}'")
        values.add(int(token, 16))
    return sorted(values)


def validate_base(value: str) -> int:
    """Parse a link base address and check it is page aligned and in range."""
    try:
        addr = int(value, 0)
    except ValueError:
        raise MaloraError(f"invalid base address '{value}' (example: 0x400000)") from None
    if not 0 <= addr < MAX_BASE or addr % PAGE_SIZE:
        raise MaloraError("base address must be 4 KiB aligned and below 2^47")
    return addr


def parse_switch(arg: str) -> Optional[bool]:
    """Parse an on/off word. Returns None for an empty argument."""
    word = arg.strip().lower()
    if not word:
        return None
    if word in ON_WORDS:
        return True
    if word in OFF_WORDS:
        return False
    raise MaloraError(f"expected on or off, got '{arg.strip()}'")
