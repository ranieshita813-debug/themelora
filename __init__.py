"""Malora: turn shellcode into verified Linux ELF executables and Android APKs."""

from malora._version import __version__
from malora.build import BuildResult, build_elf
from malora.errors import MaloraError
from malora.parsing import auto_detect_format, parse_shellcode

__all__ = [
    "BuildResult",
    "MaloraError",
    "__version__",
    "auto_detect_format",
    "build_elf",
    "parse_shellcode",
]
