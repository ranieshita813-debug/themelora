"""Disassembly and local execution of built binaries."""

from __future__ import annotations

import os
import subprocess

from malora import toolchain
from malora.constants import DEFAULT_RUN_TIMEOUT, host_arch
from malora.elf import elf_arch
from malora.errors import MaloraError


def _require_file(path: str) -> None:
    if not os.path.isfile(path):
        raise MaloraError(f"file not found: {path}")


def disassemble(path: str) -> str:
    """Return the disassembly of path as text."""
    _require_file(path)
    tool = toolchain.which("llvm-objdump", "objdump")
    if tool is None:
        raise MaloraError("no objdump found (install llvm or binutils)")
    proc = subprocess.run([tool, "-d", path], capture_output=True, text=True)
    if proc.returncode != 0:
        hint = ""
        if "can't disassemble" in proc.stderr:
            hint = " (GNU objdump lacks some architectures; install llvm-objdump)"
        raise MaloraError(f"disassembly failed: {proc.stderr.strip()}{hint}")
    return proc.stdout.expandtabs(4)


def check_runnable(path: str) -> str:
    """Confirm path is an ELF for the host architecture. Returns its absolute path."""
    _require_file(path)
    arch = elf_arch(path)
    if arch is None:
        raise MaloraError(f"not an ELF executable: {path}")
    host = host_arch()
    if arch != host:
        raise MaloraError(f"{path} targets {arch}, but this host is {host}")
    return os.path.abspath(path)


def run_binary(path: str, timeout: float = DEFAULT_RUN_TIMEOUT) -> int:
    """Run an ELF with stdin closed and a timeout. Returns its exit status."""
    target = check_runnable(path)
    try:
        proc = subprocess.run([target], stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MaloraError(f"timed out after {timeout:g}s and was killed") from None
    return proc.returncode
