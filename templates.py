"""Built-in shellcode templates for testing and demonstration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from malora.errors import MaloraError


@dataclass(frozen=True)
class Template:
    name: str
    arch: str
    description: str
    shellcode: bytes


TEMPLATES: Dict[str, Template] = {
    template.name: template
    for template in (
        Template(
            name="x86_64_execve",
            arch="x86_64",
            description="Linux x86_64 execve('/bin/sh', 0, 0)",
            # Contains NUL bytes, which makes it a useful bad-character test case.
            shellcode=bytes.fromhex("4831d248bb2f62696e2f736800534889e752574889e64831c0b03b0f05"),
        ),
        Template(
            name="aarch64_exit1",
            arch="aarch64",
            description="Linux aarch64 exit(1): mov x0,#1; mov x8,#93; svc #0",
            shellcode=bytes.fromhex("200080d2a80b80d2010000d4"),
        ),
    )
}


def get_template(name: str) -> Template:
    try:
        return TEMPLATES[name]
    except KeyError:
        raise MaloraError(f"unknown template '{name}' (see /templates)") from None
