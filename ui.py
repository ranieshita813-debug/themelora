"""Terminal UI modeled on the Claude Code CLI.

Output conventions::

    ⏺ Action title                 an action or status line, colored by outcome
      ⎿  result line               detail that belongs to the action above it
         continuation line
    ✻ Working...                   work in progress (terminals only, cleared after)

The welcome panel and the prompt framed by rules use the same visual language.
Glyphs fall back to ASCII when the output encoding is not UTF-8. Colors are
disabled when the output is not a terminal or when NO_COLOR is set.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Dict, Optional, Sequence, TextIO, Tuple

from malora._version import __version__

PANEL_WIDTH = 78
MAX_RULE_WIDTH = 100


class Theme:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    # Monochromatic grayscale theme
    ACCENT = "\033[38;2;200;200;200m"  # light gray
    TEXT = "\033[38;2;236;236;236m"    # near white
    MUTED = "\033[38;2;153;153;153m"   # medium gray
    OK = "\033[38;2;200;200;200m"      # light gray
    WARN = "\033[38;2;200;200;200m"    # light gray
    ERROR = "\033[38;2;200;200;200m"   # light gray


_TONE = {
    "accent": Theme.ACCENT,
    "ok": Theme.OK,
    "warn": Theme.WARN,
    "error": Theme.ERROR,
    "muted": Theme.MUTED,
}

_UNICODE: Dict[str, str] = {
    "bullet": "⏺",
    "result": "⎿",
    "spark": "✻",
    "ok": "✓",
    "fail": "✗",
    "h": "─",
    "v": "│",
    "tl": "╭",
    "tr": "╮",
    "bl": "╰",
    "br": "╯",
    "prompt": ">",
}
_ASCII: Dict[str, str] = {
    "bullet": "*",
    "result": "`-",
    "spark": "*",
    "ok": "+",
    "fail": "x",
    "h": "-",
    "v": "|",
    "tl": "+",
    "tr": "+",
    "bl": "+",
    "br": "+",
    "prompt": ">",
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _out(stream: Optional[TextIO]) -> TextIO:
    return stream if stream is not None else sys.stdout


def is_tty(stream: Optional[TextIO] = None) -> bool:
    isatty = getattr(_out(stream), "isatty", None)
    return bool(isatty and isatty())


def color_enabled(stream: Optional[TextIO] = None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return is_tty(stream)


def glyphs(stream: Optional[TextIO] = None) -> Dict[str, str]:
    encoding = (getattr(_out(stream), "encoding", "") or "").lower()
    return _UNICODE if "utf" in encoding else _ASCII


def paint(
    text: str,
    color: str = "",
    *,
    bold: bool = False,
    stream: Optional[TextIO] = None,
) -> str:
    if not color_enabled(stream):
        return text
    style = (Theme.BOLD if bold else "") + color
    return f"{style}{text}{Theme.RESET}" if style else text


def _emit(line: str = "", stream: Optional[TextIO] = None) -> None:
    print(line, file=_out(stream))


# ---------------------------------------------------------------------------
# Output components
# ---------------------------------------------------------------------------


def action(title: str, tone: str = "ok", stream: Optional[TextIO] = None) -> None:
    """Print a bulleted action line. tone is a key of _TONE or a raw ANSI code."""
    g = glyphs(stream)
    bullet = paint(g["bullet"], _TONE.get(tone, tone), stream=stream)
    _emit(f"{bullet} {paint(title, Theme.TEXT, bold=True, stream=stream)}", stream)


def result(
    lines: Sequence[str],
    *,
    color: str = Theme.MUTED,
    stream: Optional[TextIO] = None,
) -> None:
    """Print result lines hanging from the action above, with a ⎿ on the first."""
    g = glyphs(stream)
    for index, line in enumerate(lines or [""]):
        lead = f"  {g['result']}  " if index == 0 else "     "
        _emit(lead + paint(line, color, stream=stream), stream)


def success(message: str, stream: Optional[TextIO] = None) -> None:
    action(message, "ok", stream)


def info(message: str, stream: Optional[TextIO] = None) -> None:
    action(message, "accent", stream)


def warn(message: str, stream: Optional[TextIO] = None) -> None:
    action(message, "warn", stream)


def error(message: str, stream: Optional[TextIO] = None) -> None:
    action(message, "error", stream)


def detail(message: str, stream: Optional[TextIO] = None) -> None:
    result([message], stream=stream)


def table(rows: Sequence[Tuple[str, str]], *, stream: Optional[TextIO] = None) -> None:
    """Two-column list: accent names, muted descriptions. An empty name gives a plain note."""
    width = max((len(name) for name, _ in rows), default=0)
    for name, desc in rows:
        if name:
            line = paint(name.ljust(width), Theme.ACCENT, stream=stream)
            _emit(f"  {line}  {paint(desc, Theme.MUTED, stream=stream)}", stream)
        elif desc:
            _emit(f"  {paint(desc, Theme.MUTED, stream=stream)}", stream)
        else:
            _emit("", stream)


def key_values(rows: Sequence[Tuple[str, str]], *, stream: Optional[TextIO] = None) -> None:
    width = max((len(key) for key, _ in rows), default=0)
    for key, value in rows:
        label = paint(key.ljust(width), Theme.MUTED, stream=stream)
        _emit(f"  {label}  {paint(value, Theme.TEXT, stream=stream)}", stream)


def checklist(
    rows: Sequence[Tuple[str, Optional[str], bool]], *, stream: Optional[TextIO] = None
) -> None:
    """Rows of (label, value, required). A missing value is an error only if required."""
    g = glyphs(stream)
    width = max((len(label) for label, _, _ in rows), default=0)
    for label, value, required in rows:
        if value:
            mark = paint(g["ok"], Theme.OK, stream=stream)
            text = paint(value, Theme.MUTED, stream=stream)
        elif required:
            mark = paint(g["fail"], Theme.ERROR, stream=stream)
            text = paint("not found", Theme.ERROR, stream=stream)
        else:
            mark = paint(g["fail"], Theme.WARN, stream=stream)
            text = paint("not found (optional)", Theme.WARN, stream=stream)
        _emit(f"  {mark} {label.ljust(width)}  {text}", stream)


def hint(text: str, stream: Optional[TextIO] = None) -> None:
    _emit("  " + paint(text, Theme.MUTED, stream=stream), stream)


def rule(stream: Optional[TextIO] = None) -> None:
    width = min(shutil.get_terminal_size((80, 24)).columns, MAX_RULE_WIDTH)
    _emit(paint(glyphs(stream)["h"] * width, Theme.MUTED, stream=stream), stream)


def prompt() -> str:
    """Prompt for input(). Escape codes are wrapped so readline measures the line correctly."""
    g = glyphs()
    if not color_enabled():
        return f"{g['prompt']} "
    return f"\001{Theme.ACCENT}\002{g['prompt']}\001{Theme.RESET}\002 "


def input_box_top(stream: Optional[TextIO] = None) -> None:
    """Draw the flat top edge of a monochromatic input bar (no rounded corners)."""
    g = glyphs(stream)
    width = min(shutil.get_terminal_size((80, 24)).columns, MAX_RULE_WIDTH)
    top = g["h"] * width
    _emit(paint(top, Theme.MUTED, stream=stream), stream)


def input_box_bottom(stream: Optional[TextIO] = None) -> None:
    """Draw the flat bottom edge of a monochromatic input bar (no rounded corners)."""
    g = glyphs(stream)
    width = min(shutil.get_terminal_size((80, 24)).columns, MAX_RULE_WIDTH)
    bottom = g["h"] * width
    _emit(paint(bottom, Theme.MUTED, stream=stream), stream)


def _visible_len(text: str) -> int:
    """Length of text excluding ANSI escape codes."""
    import re as _re

    return len(_re.sub(r"\013?\033\[[0-9;]*[A-Za-z]", "", text))


def footer(items: Sequence[Tuple[str, str]], stream: Optional[TextIO] = None) -> None:
    """Draw a monochromatic footer line: left-aligned muted label + right value."""
    g = glyphs(stream)
    width = min(shutil.get_terminal_size((80, 24)).columns, MAX_RULE_WIDTH)
    for label, value in items:
        left = paint("  " + label, Theme.MUTED, stream=stream)
        right = paint(value, Theme.TEXT, stream=stream)
        pad = max(0, width - _visible_len(left) - _visible_len(right))
        _emit(left + " " * pad + right, stream)


def working(message: str, stream: Optional[TextIO] = None) -> None:
    """Show a transient progress line. It does nothing when output is not a terminal."""
    if not is_tty(stream):
        return
    g = glyphs(stream)
    out = _out(stream)
    out.write(
        f"{paint(g['spark'], Theme.ACCENT, stream=stream)} "
        f"{paint(message + '...', Theme.MUTED, stream=stream)}"
    )
    out.flush()


def working_done(stream: Optional[TextIO] = None) -> None:
    if not is_tty(stream):
        return
    out = _out(stream)
    out.write("\r\033[K")
    out.flush()


# ---------------------------------------------------------------------------
# Welcome panel
# ---------------------------------------------------------------------------


def header() -> None:
    """Draw a minimal header: only the bold name plus version, no commands."""
    _emit(paint(f"Malora v{__version__}", Theme.TEXT, bold=True))
