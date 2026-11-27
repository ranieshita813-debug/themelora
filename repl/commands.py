"""Slash commands for the interactive workbench.

Each handler receives the session and the text after the command name.
Register a command with the @command decorator.
"""

from __future__ import annotations

import sys
from typing import Callable, Dict

from malora import controlpanel, toolchain, ui
from malora.analysis import describe
from malora.constants import normalize_arch
from malora.errors import MaloraError
from malora.parsing import (
    FORMATS,
    auto_detect_format,
    parse_badchars,
    parse_shellcode,
    parse_switch,
    validate_base,
)
from malora.runner import check_runnable, disassemble, run_binary
from malora.session import Session, build_payload
from malora.templates import TEMPLATES, get_template

DISASM_LINE_LIMIT = 60

Handler = Callable[[Session, str], None]
COMMANDS: Dict[str, Handler] = {}


class ExitRepl(Exception):
    """Raised by /exit to leave the workbench loop."""


def command(*names: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        for name in names:
            COMMANDS[name] = fn
        return fn

    return register


def dispatch(session: Session, name: str, arg: str) -> None:
    handler = COMMANDS.get(name)
    if handler is None:
        raise MaloraError(f"unknown command '{name}' (try /help)")
    handler(session, arg)


def build_text(session: Session, text: str) -> None:
    """Treat a line of input as shellcode and build it."""
    fmt = session.fmt or auto_detect_format(text)
    data = parse_shellcode(text, fmt)
    ui.info(f"Shellcode {len(data)} bytes ({fmt})")
    build_payload(session, data)


def _on_off(value: bool) -> str:
    return "ON" if value else "OFF"


def _toggle(session: Session, attr: str, arg: str, label: str) -> None:
    value = parse_switch(arg)
    if value is None:
        ui.info(f"{label} is {_on_off(getattr(session, attr))}")
        return
    setattr(session, attr, value)
    ui.success(f"{label} {'enabled' if value else 'disabled'}")


@command("/help", "/?")
def cmd_help(session: Session, arg: str) -> None:
    ui.action("Commands", "accent")
    ui.table(
        [
            ("/help", "show this list"),
            ("/status", "show session settings"),
            ("/arch <aarch64|x86_64>", "set target architecture"),
            ("/format <fmt|auto>", "input format: hex, c, base64, raw, auto"),
            ("/output <name>", "output name; a .apk name enables APK mode"),
            ("/base <addr>", "link base address, e.g. 0x400000"),
            ("/apk <on|off>", "toggle APK packaging"),
            ("/stub <on|off>", "toggle the exit syscall stub"),
            ("/strip <on|off>", "toggle symbol stripping"),
            ("/installable <on|off>", "installable vs placeholder APK"),
            ("/settings [name]", "view or change a session setting"),
            ("/plugins [name]", "list plugins or view a plugin's details"),
            ("/tools [name]", "view toolchain status"),
            ("/badchars [list|clear]", "show or set bad bytes, e.g. 00,0a,0d"),
            ("/templates", "list built-in templates"),
            ("/load <template>", "build a built-in template"),
            ("/inspect <shellcode>", "analyze without building"),
            ("/disasm [file]", "disassemble the last build or a file"),
            ("/run [file]", "run a local ELF (host arch, 10 s limit)"),
            ("/doctor", "check the toolchain"),
            ("/cp", "serve a read-only web control panel URL"),
            ("/clear", "clear the screen"),
            ("/exit", "quit"),
            ("", ""),
            ("", "Any other input is treated as shellcode and built right away."),
        ]
    )


@command("/status")
def cmd_status(session: Session, arg: str) -> None:
    ui.action("Session", "accent")
    ui.key_values(
        [
            ("Architecture", session.arch),
            ("Output", session.output),
            ("Base address", session.base),
            ("APK mode", _on_off(session.apk)),
            ("Exit stub", _on_off(session.exit_stub)),
            ("Strip", _on_off(session.strip)),
            ("Input format", session.fmt or "auto-detect"),
            ("Bad bytes", " ".join(f"{b:02x}" for b in session.badchars) or "none"),
            ("Last output", session.last_output or "none"),
        ]
    )


@command("/arch")
def cmd_arch(session: Session, arg: str) -> None:
    if not arg:
        ui.info(f"Architecture: {session.arch}")
        return
    arch = normalize_arch(arg)
    if arch is None:
        raise MaloraError("arch must be aarch64 or x86_64")
    session.arch = arch
    ui.success(f"Architecture set to {arch}")


@command("/format")
def cmd_format(session: Session, arg: str) -> None:
    if not arg:
        ui.info(f"Input format: {session.fmt or 'auto-detect'}")
        return
    choice = arg.lower()
    if choice != "auto" and choice not in FORMATS:
        raise MaloraError("format must be hex, c, base64, raw, or auto")
    session.fmt = None if choice == "auto" else choice
    ui.success(f"Input format set to {choice}")


@command("/output")
def cmd_output(session: Session, arg: str) -> None:
    if not arg:
        ui.info(f"Output: {session.output}")
        return
    session.output = arg
    if arg.endswith(".apk"):
        session.apk = True
    ui.success(f"Output set to {arg}")


@command("/base")
def cmd_base(session: Session, arg: str) -> None:
    if not arg:
        ui.info(f"Base address: {session.base}")
        return
    validate_base(arg)
    session.base = arg
    ui.success(f"Base address set to {arg}")


@command("/apk")
def cmd_apk(session: Session, arg: str) -> None:
    _toggle(session, "apk", arg, "APK mode")


@command("/stub")
def cmd_stub(session: Session, arg: str) -> None:
    _toggle(session, "exit_stub", arg, "Exit stub")


@command("/strip")
def cmd_strip(session: Session, arg: str) -> None:
    _toggle(session, "strip", arg, "Symbol stripping")


@command("/installable")
def cmd_installable(session: Session, arg: str) -> None:
    _toggle(session, "installable", arg, "Installable APK")


@command("/settings")
def cmd_settings(session: Session, arg: str) -> None:
    """View or toggle session settings."""
    if not arg:
        ui.action("Settings", "accent")
        ui.key_values(
            [
                ("Architecture", session.arch),
                ("Output", session.output),
                ("Base address", session.base),
                ("APK mode", _on_off(session.apk)),
                ("Exit stub", _on_off(session.exit_stub)),
                ("Strip", _on_off(session.strip)),
                ("Input format", session.fmt or "auto-detect"),
                ("Bad bytes", " ".join(f"{b:02x}" for b in session.badchars) or "none"),
                ("Installable APK", _on_off(session.installable)),
            ]
        )
        return
    choice = arg.lower()
    if choice in ("arch", "architecture"):
        ui.info(f"Architecture: {session.arch} (use /arch <aarch64|x86_64> to change)")
    elif choice == "output":
        ui.info(f"Output: {session.output} (use /output <name> to change)")
    elif choice == "base":
        ui.info(f"Base address: {session.base} (use /base <addr> to change)")
    elif choice == "apk":
        ui.info(f"APK mode: {_on_off(session.apk)} (use /apk <on|off> to change)")
    elif choice == "stub":
        ui.info(f"Exit stub: {_on_off(session.exit_stub)} (use /stub <on|off> to change)")
    elif choice == "strip":
        ui.info(f"Strip: {_on_off(session.strip)} (use /strip <on|off> to change)")
    elif choice == "format":
        ui.info(f"Input format: {session.fmt or 'auto-detect'} (use /format <fmt> to change)")
    elif choice == "badchars":
        shown = " ".join(f"{b:02x}" for b in session.badchars) or "none"
        ui.info(f"Bad bytes: {shown} (use /badchars [list|clear] to change)")
    elif choice == "installable":
        ui.info(f"Installable APK: {_on_off(session.installable)} (use /installable <on|off> to change)")
    else:
        ui.error(f"unknown setting '{arg}' (try /settings)")


@command("/plugins")
def cmd_plugins(session: Session, arg: str) -> None:
    """List available plugins (built-in templates are the extensible payload set)."""
    if not arg:
        ui.action("Plugins", "accent")
        ui.table([(t.name, f"{t.description} ({t.arch})") for t in TEMPLATES.values()])
        return
    template = get_template(arg) if arg in TEMPLATES else None
    if template is None:
        ui.error(f"unknown plugin '{arg}' (see /plugins)")
        return
    ui.info(f"Plugin {template.name}: {template.description} ({template.arch})")


@command("/tools")
def cmd_tools(session: Session, arg: str) -> None:
    """View toolchain status."""
    if not arg:
        ui.action("Tools", "accent")
        ui.checklist(toolchain.doctor_checks())
        return
    ui.error(f"unknown tool '{arg}' (see /tools)")


@command("/badchars")
def cmd_badchars(session: Session, arg: str) -> None:
    if not arg:
        shown = " ".join(f"{b:02x}" for b in session.badchars) or "none"
        ui.info(f"bad bytes: {shown}")
        return
    if arg.lower() in ("none", "clear", "off"):
        session.badchars = []
    else:
        session.badchars = parse_badchars(arg)
    ui.success(f"bad bytes set ({len(session.badchars)} value(s))")


@command("/templates")
def cmd_templates(session: Session, arg: str) -> None:
    ui.action("Templates", "accent")
    ui.table([(t.name, f"{t.description} ({t.arch})") for t in TEMPLATES.values()])


@command("/load")
def cmd_load(session: Session, arg: str) -> None:
    template = get_template(arg)
    session.arch = template.arch
    ui.info(f"Loading {template.name}: {len(template.shellcode)} bytes, {template.arch}")
    build_payload(session, template.shellcode)


@command("/inspect")
def cmd_inspect(session: Session, arg: str) -> None:
    if not arg:
        raise MaloraError("usage: /inspect <shellcode>")
    fmt = session.fmt or auto_detect_format(arg)
    data = parse_shellcode(arg, fmt)
    ui.action(f"Inspect {len(data)} bytes ({fmt})", "accent")
    ui.result(describe(data, fmt, session.badchars))


@command("/disasm")
def cmd_disasm(session: Session, arg: str) -> None:
    target = arg or session.last_output
    if not target:
        raise MaloraError("nothing to disassemble; build something or pass a file")
    if target.endswith(".apk"):
        raise MaloraError("APK containers cannot be disassembled directly")
    lines = disassemble(target).splitlines()
    shown = lines[:DISASM_LINE_LIMIT]
    if len(lines) > DISASM_LINE_LIMIT:
        shown.append(f"... {len(lines) - DISASM_LINE_LIMIT} more lines")
    ui.action(f"Disassemble {target}", "accent")
    ui.result(shown)


@command("/run")
def cmd_run(session: Session, arg: str) -> None:
    target = arg or session.last_output
    if not target:
        raise MaloraError("nothing to run; build an ELF first")
    if target.endswith(".apk"):
        raise MaloraError("APK packages cannot be run on this host")
    check_runnable(target)
    ui.action(f"Run {target}", "accent")
    ui.result([f"exited with status {run_binary(target)}"])


@command("/doctor")
def cmd_doctor(session: Session, arg: str) -> None:
    ui.action("Toolchain", "accent")
    ui.checklist(toolchain.doctor_checks())


@command("/clear")
def cmd_clear(session: Session, arg: str) -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    ui.header()


@command("/cp")
def cmd_cp(session: Session, arg: str) -> None:
    """Serve a read-only web control panel and print its URL."""
    url = controlpanel.serve(session)
    ui.action("Control panel", "accent")
    ui.result([f"URL: {url}", "Open it in your browser (read-only status)."])


@command("/exit", "/quit", "/q")
def cmd_exit(session: Session, arg: str) -> None:
    raise ExitRepl
