"""Static analysis of shellcode: entropy, bad bytes, and hex dumps."""

from __future__ import annotations

import math
from collections import Counter
from typing import Dict, Iterable, List, Optional

BYTES_PER_DUMP_ROW = 16
MAX_LISTED_OFFSETS = 12


def calculate_entropy(data: bytes) -> float:
    """Shannon entropy in bits per byte, from 0.0 to 8.0."""
    if not data:
        return 0.0
    n = len(data)
    entropy = 0.0
    for count in Counter(data).values():
        p = count / n
        entropy -= p * math.log2(p)
    return round(entropy, 3)


def find_badchars(data: bytes, badchars: Iterable[int]) -> Dict[int, List[int]]:
    """Map each bad byte value present in data to the offsets where it occurs."""
    wanted = set(badchars)
    hits: Dict[int, List[int]] = {}
    for offset, byte in enumerate(data):
        if byte in wanted:
            hits.setdefault(byte, []).append(offset)
    return dict(sorted(hits.items()))


def badchar_warning(data: bytes, badchars: Iterable[int]) -> Optional[str]:
    """Return a one-line warning if any bad byte is present, otherwise None."""
    hits = find_badchars(data, badchars)
    if not hits:
        return None
    names = ", ".join(f"{value:02x}" for value in hits)
    return f"payload contains bad byte(s): {names}"


def hexdump_lines(data: bytes) -> List[str]:
    """Format data as offset, hex bytes, and an ASCII preview."""
    lines = []
    for start in range(0, len(data), BYTES_PER_DUMP_ROW):
        chunk = data[start : start + BYTES_PER_DUMP_ROW]
        hex_part = " ".join(f"{b:02x}" for b in chunk).ljust(BYTES_PER_DUMP_ROW * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{start:04x}: {hex_part} |{ascii_part}|")
    return lines


def describe(data: bytes, fmt: str, badchars: Iterable[int]) -> List[str]:
    """Build the full inspection report as display lines."""
    badchars = list(badchars)
    hits = find_badchars(data, badchars)
    tracked = " ".join(f"{b:02x}" for b in badchars) or "none"
    if hits:
        bad_summary = f"{len(hits)} value(s) present (tracked: {tracked})"
    else:
        bad_summary = f"none present (tracked: {tracked})"
    lines = [
        f"Length    : {len(data)} bytes",
        f"Format    : {fmt}",
        f"Entropy   : {calculate_entropy(data)} / 8.0 (near 8 suggests packed or encrypted)",
        f"Bad bytes : {bad_summary}",
    ]
    for value, offsets in hits.items():
        shown = ", ".join(f"0x{o:x}" for o in offsets[:MAX_LISTED_OFFSETS])
        extra = len(offsets) - MAX_LISTED_OFFSETS
        suffix = f" (+{extra} more)" if extra > 0 else ""
        lines.append(f"  {value:02x} at offsets: {shown}{suffix}")
    lines.append("Hexdump:")
    lines.extend(hexdump_lines(data))
    return lines
