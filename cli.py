"""Command-line entry point for malora."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional, Tuple

from malora import toolchain, ui
from malora._version import __version__
from malora.constants import (
    DEFAULT_BADCHARS,
    DEFAULT_BASE,
    DEFAULT_OUTPUT,
    SUPPORTED_ARCHES,
    host_arch,
)
from malora.errors import MaloraError
from malora.parsing import auto_detect_format, parse_badchars, parse_shellcode
from malora.repl import run_repl
from malora.runner import run_binary
from malora.session import Session, build_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="malora",
        description="Convert shellcode into a standalone ELF or an Android APK container.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  malora                                  interactive workbench
  malora 90909090                         hex shellcode to ELF
  malora -f c '\\x31\\xc0\\x31\\xdb'         C-style escapes
  malora -f base64 AAAA                   force base64 decoding
  malora --file sc.bin --badchars 00,0a   raw binary file, flag bad bytes
  malora 90909090 --apk -o app            package as an APK (aarch64)
  malora --doctor                         check the toolchain
""",
    )
    parser.add_argument(
        "shellcode",
        nargs="?",
        help="shellcode text (hex, base64, or \\xNN); '-' or omit to read stdin",
    )
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="output ELF or APK name")
    parser.add_argument(
        "-f",
        "--format",
        choices=["hex", "base64", "c", "raw"],
        help="input format (default: auto-detect; raw for --file)",
    )
    parser.add_argument("--file", help="read shellcode bytes from a file")
    parser.add_argument("--apk", action="store_true", help="package as an Android APK container")
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
        "--badchars", help='bad bytes to flag, for example "00,0a,0d" (default: 00)'
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
    parser.add_argument("--doctor", action="store_true", help="check the toolchain and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="log compiler commands")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _load_shellcode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Tuple[bytes, str]:
    """Read shellcode from --file, the positional argument, or stdin."""
    if args.file:
        if args.shellcode not in (None, "-"):
            parser.error("cannot combine --file with a positional shellcode argument")
        with open(args.file, "rb") as fh:
            raw = fh.read()
        fmt = args.format or "raw"
        if fmt == "raw":
            return raw, fmt
        return parse_shellcode(raw.decode("latin-1"), fmt), fmt

    text = args.shellcode if args.shellcode not in (None, "-") else sys.stdin.read()
    fmt = args.format or auto_detect_format(text)
    return parse_shellcode(text, fmt), fmt


def _build_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    data, fmt = _load_shellcode(args, parser)
    if not data:
        raise MaloraError("shellcode is empty")

    badchars: List[int] = (
        parse_badchars(args.badchars) if args.badchars is not None else list(DEFAULT_BADCHARS)
    )
    arch = args.arch or ("aarch64" if args.apk else host_arch())
    session = Session(
        arch=arch,
        fmt=fmt,
        output=args.output,
        base=args.base,
        exit_stub=not args.no_exit_stub,
        strip=args.strip,
        apk=args.apk,
        keep_asm=args.keep,
        installable=not args.no_installable,
        badchars=badchars,
    )

    size = f"{len(data)} byte" if len(data) == 1 else f"{len(data)} bytes"
    ui.info(f"Shellcode {size} ({fmt}) for {arch}")
    path = build_payload(session, data)

    if args.run:
        ui.action(f"Run {path}", "accent")
        ui.result([f"exited with status {run_binary(path)}"])
    return 0


def _configure_logging(verbose: bool) -> None:
    logger = logging.getLogger("malora")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.doctor:
        ui.action("Toolchain", "accent")
        ui.checklist(toolchain.doctor_checks())
        return 0

    if args.shellcode is None and args.file is None and sys.stdin.isatty():
        run_repl()
        return 0

    try:
        return _build_command(args, parser)
    except MaloraError as exc:
        ui.error(str(exc), stream=sys.stderr)
        return 1
    except KeyboardInterrupt:
        ui.warn("Interrupted")
        return 130
