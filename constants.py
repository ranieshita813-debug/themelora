"""Shared constants and small host helpers."""

from __future__ import annotations

import platform

SUPPORTED_ARCHES = ("x86_64", "aarch64")

ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}

ARCH_TRIPLE = {
    "x86_64": "x86_64-unknown-linux-gnu",
    "aarch64": "aarch64-unknown-linux-gnu",
}

# e_machine values from the ELF specification.
ELF_MACHINE = {"x86_64": 0x3E, "aarch64": 0xB7}

PT_LOAD = 1
PAGE_SIZE = 0x1000
MAX_BASE = 1 << 47

DEFAULT_BASE = "0x400000"
DEFAULT_OUTPUT = "malora_out"
DEFAULT_RUN_TIMEOUT = 10.0
DEFAULT_BADCHARS = (0x00,)

ON_WORDS = frozenset({"on", "true", "1", "yes", "enable", "enabled"})
OFF_WORDS = frozenset({"off", "false", "0", "no", "disable", "disabled"})

# Exit syscall appended after the payload so the process terminates cleanly.
EXIT_STUBS = {
    "x86_64": ("mov eax, 60", "xor edi, edi", "syscall"),
    "aarch64": ("mov x8, #93", "mov x0, #0", "svc #0"),
}


def normalize_arch(name: str) -> str | None:
    """Map an architecture alias to its canonical name, or None if unknown."""
    return ARCH_ALIASES.get(name.lower())


def host_arch() -> str:
    """Return the canonical architecture of the machine running Malora."""
    return ARCH_ALIASES.get(platform.machine().lower(), "x86_64")
