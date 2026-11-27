"""Session state shared by the command line and the REPL, and the build dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from malora import ui
from malora.analysis import badchar_warning
from malora.apk import ApkResult, build_apk
from malora.build import BuildResult, build_elf
from malora.constants import DEFAULT_BADCHARS, DEFAULT_BASE, DEFAULT_OUTPUT, host_arch


@dataclass
class Session:
    arch: str = field(default_factory=host_arch)
    fmt: Optional[str] = None
    output: str = DEFAULT_OUTPUT
    base: str = DEFAULT_BASE
    exit_stub: bool = True
    strip: bool = False
    apk: bool = False
    installable: bool = True
    keep_asm: bool = False
    badchars: List[int] = field(default_factory=lambda: list(DEFAULT_BADCHARS))
    last_output: Optional[str] = None


def warn_badchars(data: bytes, badchars: List[int]) -> None:
    warning = badchar_warning(data, badchars)
    if warning:
        ui.warn(f"{warning} (building anyway)")


def _plural_bytes(count: int) -> str:
    return f"{count} byte" if count == 1 else f"{count} bytes"


def report_build(result: BuildResult) -> None:
    ui.success(f"Built {result.path}")
    lines = [
        f"{_plural_bytes(result.size)} · {result.arch} · "
        f"entry 0x{result.entry:x} · file offset 0x{result.payload_offset:x}",
        "payload verified",
    ]
    if result.asm_path:
        lines.append(f"assembly saved to {result.asm_path}")
    ui.result(lines)
    for message in result.warnings:
        ui.warn(message)


def report_apk(apk: ApkResult) -> None:
    ui.success(f"Built APK {apk.path}")
    ui.result([f"{_plural_bytes(apk.size)} · aarch64 container"])
    for message in apk.warnings:
        ui.warn(message)


def build_payload(session: Session, shellcode: bytes) -> str:
    """Build shellcode with the session settings, report it, and return the output path."""
    warn_badchars(shellcode, session.badchars)
    ui.working("Assembling and verifying")
    try:
        if session.apk:
            apk = build_apk(
                shellcode,
                session.output,
                arch=session.arch,
                add_exit_stub=session.exit_stub,
                installable=session.installable,
            )
        else:
            result = build_elf(
                shellcode,
                session.output,
                arch=session.arch,
                base=session.base,
                strip=session.strip,
                add_exit_stub=session.exit_stub,
                keep_asm=session.keep_asm,
            )
    finally:
        ui.working_done()

    if session.apk:
        report_apk(apk)
        session.last_output = apk.path
        return apk.path
    report_build(result)
    session.last_output = result.path
    return result.path
