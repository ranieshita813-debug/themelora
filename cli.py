"""Professional command-line interface for Malora.

Turns shellcode into verified Linux ELF executables and Android APK containers.

Usage::

    malora <shellcode> [options]      build directly from the command line
    malora build <shellcode> [options] explicit build subcommand
    malora repl                        interactive workbench
    malora doctor                      check the toolchain
    malora cp                          serve the web control panel
    malora config                      show/edit configuration
    malora --version                   print version and exit
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

try:
    from rich.argparse import RichHelpFormatter  # type: ignore[attr-defined]
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _RICH = True
except Exception:  # pragma: no cover - rich optional
    RichHelpFormatter = argparse.HelpFormatter  # type: ignore[assignment]

    class Console:  # minimal stand-in
        def print(self, *args, **kwargs):
            print(*args)

        def status(self, *args, **kwargs):
            class _Ctx:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            return _Ctx()

    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    _RICH = False

from malora import controlpanel, ui
from malora._version import __version__
from malora.build import build_elf
from malora.constants import (
    DEFAULT_BADCHARS,
    DEFAULT_BASE,
    DEFAULT_OUTPUT,
    DEFAULT_RUN_TIMEOUT,
    SUPPORTED_ARCHES,
    host_arch,
)
from malora.errors import MaloraError
from malora.parsing import (
    FORMATS,
    auto_detect_format,
    parse_badchars,
    parse_shellcode,
    validate_base,
)
from malora.repl.app import run_repl
from malora.runner import check_runnable, run_binary
from malora.session import Session, build_payload, report_apk, report_build

APP_NAME = "malora"

# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

console = Console()


def _build_console(no_color: bool, force_color: bool) -> Console:
    if force_color:
        return Console(force_terminal=True, color_system="standard")
    if no_color:
        return Console(no_color=True)
    return Console()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

_BUILD_EPILOG = """examples:
  malora 90909090                                   hex shellcode to ELF
  malora -f c '\\x31\\xc0\\x31\\xdb'                 C-style escapes
  malora -f base64 AAAA                             force base64 decoding
  malora --file sc.bin --badchars 00,0a,0d          raw binary file, flag bad bytes
  malora 90909090 --apk -o app                      package as an APK (aarch64)
  malora --doctor                                   check the toolchain
"""


def _add_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "shellcode",
        nargs="?",
        help="shellcode text (hex, base64, or \\xNN); '-' or omit to read stdin",
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT, help="output ELF or APK name"
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=list(FORMATS) + ["auto"],
        default="auto",
        help="input format (default: auto-detect; raw for --file)",
    )
    parser.add_argument("--file", help="read shellcode bytes from a file")
    parser.add_argument(
        "--apk",
        action="store_true",
        help="package as an Android APK container",
    )
    parser.add_argument(
        "--no-installable",
        action="store_true",
        help="with --apk, emit a legacy non-installable placeholder APK",
    )
    parser.add_argument(
        "--arch",
        choices=list(SUPPORTED_ARCHES),
        help="target architecture (default: host; aarch64 for APK)",
    )
    parser.add_argument(
        "--base", default=DEFAULT_BASE, help=f"link base address (default: {DEFAULT_BASE})"
    )
    parser.add_argument(
        "--badchars", help='bad bytes to flag, e.g. "00,0a,0d" (default: 00)'
    )
    parser.add_argument(
        "--no-exit-stub",
        action="store_true",
        help="do not append an exit syscall after the shellcode",
    )
    parser.add_argument("--strip", action="store_true", help="strip symbols from the ELF")
    parser.add_argument(
        "--keep", action="store_true", help="save the generated assembly as OUTPUT.S"
    )
    parser.add_argument("--run", action="store_true", help="run the ELF after building")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=(
            "Turn shellcode into verified Linux ELF executables and Android APK containers."
        ),
        formatter_class=RichHelpFormatter,
        epilog=_BUILD_EPILOG,
    )
    parser.add_argument(
        "--config", help="path to configuration file (default: ~/.config/malora/config.toml)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log compiler commands"
    )
    parser.add_argument("--no-color", action="store_true", help="disable colored output")
    parser.add_argument(
        "--color", action="store_true", help="force colored output"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command", help="command to run")

    build_cmd = sub.add_parser(
        "build", help="build shellcode into an ELF or APK", formatter_class=RichHelpFormatter
    )
    _add_build_args(build_cmd)

    sub.add_parser(
        "repl", help="start the interactive workbench", formatter_class=RichHelpFormatter
    )
    sub.add_parser(
        "doctor", help="check the toolchain and exit", formatter_class=RichHelpFormatter
    )
    sub.add_parser(
        "cp", help="serve the read-only web control panel", formatter_class=RichHelpFormatter
    )
    sub.add_parser(
        "config", help="show or edit configuration", formatter_class=RichHelpFormatter
    )

    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_shellcode(args: argparse.Namespace) -> bytes:
    """Read shellcode from --file, the positional argument, or stdin."""
    if args.file:
        with open(args.file, "rb") as fh:
            raw = fh.read()
        fmt = args.format if args.format != "auto" else "raw"
        if fmt == "raw":
            return raw
        return parse_shellcode(raw.decode("latin-1"), fmt)

    text = args.shellcode if args.shellcode not in (None, "-") else sys.stdin.read()
    fmt = args.format if args.format != "auto" else auto_detect_format(text)
    return parse_shellcode(text, fmt)


def _make_session(args: argparse.Namespace) -> Session:
    badchars: List[int] = (
        parse_badchars(args.badchars) if args.badchars is not None else list(DEFAULT_BADCHARS)
    )
    arch = args.arch or ("aarch64" if args.apk else host_arch())
    return Session(
        arch=arch,
        fmt=None if args.format == "auto" else args.format,
        output=args.output,
        base=args.base,
        exit_stub=not args.no_exit_stub,
        strip=args.strip,
        apk=args.apk,
        installable=not args.no_installable,
        keep_asm=args.keep,
        badchars=badchars,
    )


def _build_and_report(data: bytes, args: argparse.Namespace, console: Console) -> int:
    if not data:
        if _RICH:
            console.print("[red]error:[/red] shellcode is empty")
        else:
            print("error: shellcode is empty")
        return 1

    session = _make_session(args)

    size = f"{len(data)} byte" if len(data) == 1 else f"{len(data)} bytes"
    ui.info(f"Shellcode {size} ({session.fmt or 'auto'}) for {session.arch}")

    if _RICH:
        with console.status("[bold green]Assembling and verifying[/bold green]", spinner="dots"):
            path = build_payload(session, data)
    else:
        print("Assembling and verifying...")
        path = build_payload(session, data)

    if _RICH:
        table = Table(title="Build result", show_header=False, box=None)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Output", path)
        table.add_row("Architecture", session.arch)
        table.add_row("Size", size)
        table.add_row("APK", "yes" if session.apk else "no")
        console.print(table)
    else:
        print("Build result:")
        print(f"  Output:      {path}")
        print(f"  Architecture: {session.arch}")
        print(f"  Size:        {size}")
        print(f"  APK:         {'yes' if session.apk else 'no'}")

    if args.run:
        if session.apk:
            if _RICH:
                console.print("[yellow]warn:[/yellow] APK packages cannot be run on this host")
            else:
                print("warn: APK packages cannot be run on this host")
        else:
            check_runnable(path)
            ui.action(f"Run {path}", "accent")
            ui.result([f"exited with status {run_binary(path)}"])
    return 0


# ---------------------------------------------------------------------------
# Subcommand runners
# ---------------------------------------------------------------------------


def _cmd_build(args: argparse.Namespace, console: Console) -> int:
    data = _load_shellcode(args)
    return _build_and_report(data, args, console)


def _cmd_repl(args: argparse.Namespace, console: Console) -> int:
    run_repl()
    return 0


def _cmd_doctor(args: argparse.Namespace, console: Console) -> int:
    from malora import toolchain

    ui.action("Toolchain", "accent")
    ui.checklist(toolchain.doctor_checks())
    return 0


def _cmd_cp(args: argparse.Namespace, console: Console) -> int:
    session = _make_session(args)
    url = controlpanel.serve(session)
    ui.action("Control panel", "accent")
    ui.result([f"URL: {url}", "Open it in your browser (read-only status)."])
    if _RICH:
        console.print("[dim]Press Ctrl-C to stop.[/dim]")
    else:
        print("Press Ctrl-C to stop.")
    try:
        import signal

        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        controlpanel.stop_panel()
    return 0


def _cmd_config(args: argparse.Namespace, console: Console) -> int:
    from pathlib import Path

    from platformdirs import user_config_dir

    config_dir = Path(user_config_dir(APP_NAME))
    config_path = Path(args.config) if args.config else config_dir / "config.toml"

    if _RICH:
        table = Table(title="Configuration", show_header=False, box=None)
        table.add_column("Key", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("Config file", str(config_path))
        table.add_row("Exists", "yes" if config_path.exists() else "no")
        table.add_row("Version", __version__)
        console.print(table)
    else:
        print("Configuration:")
        print(f"  Config file: {config_path}")
        print(f"  Exists: {'yes' if config_path.exists() else 'no'}")
        print(f"  Version: {__version__}")
    if not config_path.exists():
        if _RICH:
            console.print(f"[dim]Create {config_path} to customize defaults.[/dim]")
        else:
            print(f"Create {config_path} to customize defaults.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = _build_console(args.no_color, args.color)

    if args.command in (None, "repl", "cp"):
        console.print(
            Panel.fit(
                f"[bold]{APP_NAME}[/bold] v{__version__}\n"
                "[dim]Turn shellcode into verified Linux ELF executables and Android APK containers.[/dim]",
                border_style="cyan",
            )
        )

    if args.command is None:
        if args.shellcode is None and args.file is None and sys.stdin.isatty():
            parser.print_help()
            return 0
        return _cmd_build(args, console)

    if args.command == "build":
        return _cmd_build(args, console)
    if args.command == "repl":
        return _cmd_repl(args, console)
    if args.command == "doctor":
        return _cmd_doctor(args, console)
    if args.command == "cp":
        return _cmd_cp(args, console)
    if args.command == "config":
        return _cmd_config(args, console)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
