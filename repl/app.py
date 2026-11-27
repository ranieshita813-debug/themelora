"""Input loop for the interactive workbench, styled after the Claude Code prompt."""

from __future__ import annotations

import sys

from malora import ui
from malora.errors import MaloraError
from malora.repl.commands import ExitRepl, build_text, dispatch
from malora.session import Session


def _enable_line_editing() -> None:
    try:
        import readline  # noqa: F401  (imported for its side effect)
    except ImportError:
        pass


def _status_line(session: Session) -> str:
    parts = ["? /help for commands", session.arch]
    if session.apk:
        parts.append("APK mode")
    parts.append(f"output {session.output}")
    return " · ".join(parts)


def _show_footer(session: Session, stream) -> None:
    ui.footer(
        [
            ("arch", session.arch),
            ("fmt", session.fmt or "auto"),
            ("apk", "on" if session.apk else "off"),
            ("output", session.output),
        ],
        stream=stream,
    )


def run_repl() -> None:
    """Run the interactive loop until the user exits."""
    _enable_line_editing()
    session = Session()
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    ui.header()
    print()
    ui.hint("Type shellcode to build it, or /help for commands. Ctrl-D to exit.")
    print()

    while True:
        ui.rule()
        ui.input_box_top()
        try:
            line = input(ui.prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            ui.input_box_bottom()
            ui.info("Goodbye")
            return
        ui.input_box_bottom()
        ui.rule()
        ui.hint(_status_line(session))
        _show_footer(session, sys.stdout)
        if not line:
            continue

        try:
            if line.startswith("/"):
                parts = line.split(maxsplit=1)
                arg = parts[1].strip() if len(parts) > 1 else ""
                dispatch(session, parts[0].lower(), arg)
            else:
                build_text(session, line)
        except ExitRepl:
            ui.info("Goodbye")
            return
        except MaloraError as exc:
            ui.error(str(exc))
        except KeyboardInterrupt:
            ui.warn("Interrupted")
        except Exception as exc:  # keep the session alive on unexpected failures
            ui.error(f"unexpected error: {type(exc).__name__}: {exc}")
        print()
