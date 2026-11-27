"""Locate and invoke the external toolchain: clang, lld, objdump, and strip."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from typing import List, Optional, Tuple

from malora.constants import ARCH_TRIPLE, host_arch
from malora.errors import MaloraError

log = logging.getLogger(__name__)

REQUIRED_TOOLS = ("clang",)
OPTIONAL_TOOLS = ("ld.lld", "llvm-objdump", "objdump", "llvm-strip", "strip", "apksigner")


def which(*names: str) -> Optional[str]:
    """Return the path of the first tool found on PATH, or None."""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def require(name: str, hint: str = "") -> str:
    path = shutil.which(name)
    if path is None:
        message = f"required tool '{name}' not found in PATH"
        raise MaloraError(f"{message} ({hint})" if hint else message)
    return path


def target_flags(arch: str) -> List[str]:
    """Extra clang flags needed to target arch from the host, if they differ."""
    if arch == host_arch():
        return []
    return [f"--target={ARCH_TRIPLE[arch]}"]


def link_flags(arch: str) -> List[str]:
    """Linker selection. lld is preferred because GNU ld may lack the target."""
    if which("ld.lld"):
        return ["-fuse-ld=lld"]
    if arch != host_arch():
        raise MaloraError(f"cross-linking to {arch} requires lld (apt install lld)")
    return []


def run(cmd: List[str], what: str) -> subprocess.CompletedProcess:
    """Run an external command, raising MaloraError with stderr on failure."""
    log.debug("running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MaloraError(f"{what} failed:\n{proc.stderr.strip()}")
    return proc


def doctor_checks() -> List[Tuple[str, Optional[str], bool]]:
    """Return (label, value, required) rows describing the toolchain."""
    checks: List[Tuple[str, Optional[str], bool]] = [
        ("host arch", f"{host_arch()} ({platform.machine()})", True),
    ]
    for tool in REQUIRED_TOOLS + OPTIONAL_TOOLS:
        checks.append((tool, which(tool), tool in REQUIRED_TOOLS))
    clang = which("clang")
    if clang:
        proc = subprocess.run([clang, "--version"], capture_output=True, text=True)
        first = proc.stdout.splitlines()[0] if proc.stdout else "unknown"
        checks.append(("clang version", first, True))
    return checks
