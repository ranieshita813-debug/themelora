"""Inspect and verify the ELF files produced by the build pipeline."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

from malora.constants import ELF_MACHINE, PT_LOAD
from malora.errors import MaloraError

ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
_HEADER_SIZE = 64
_PHDR_FORMAT = "<IIQQQQQQ"  # one 64-bit program header (56 bytes)


@dataclass(frozen=True)
class ElfCheck:
    """Result of a successful verification."""

    entry: int
    payload_offset: int


def _arch_for_machine(machine: int) -> str:
    for arch, code in ELF_MACHINE.items():
        if code == machine:
            return arch
    return f"unknown(0x{machine:x})"


def elf_arch(path: str) -> Optional[str]:
    """Return the architecture of an ELF file, or None if the file is not ELF."""
    with open(path, "rb") as fh:
        head = fh.read(20)
    if len(head) < 20 or head[:4] != ELF_MAGIC:
        return None
    (machine,) = struct.unpack_from("<H", head, 18)
    return _arch_for_machine(machine)


def verify_elf(path: str, arch: str, payload: bytes) -> ElfCheck:
    """Confirm that path is a valid ELF for arch whose entry point begins with payload."""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < _HEADER_SIZE or data[:4] != ELF_MAGIC:
        raise MaloraError("output is not an ELF file")
    if data[4] != ELFCLASS64:
        raise MaloraError("output is not a 64-bit ELF")

    try:
        (machine,) = struct.unpack_from("<H", data, 18)
        if machine != ELF_MACHINE[arch]:
            found = _arch_for_machine(machine)
            raise MaloraError(f"ELF machine is {found}, expected {arch}")
        (entry,) = struct.unpack_from("<Q", data, 24)
        (phoff,) = struct.unpack_from("<Q", data, 32)
        phentsize, phnum = struct.unpack_from("<HH", data, 54)

        for index in range(phnum):
            fields = struct.unpack_from(_PHDR_FORMAT, data, phoff + index * phentsize)
            p_type, p_offset, p_vaddr, p_filesz = fields[0], fields[2], fields[3], fields[5]
            if p_type != PT_LOAD or not p_vaddr <= entry < p_vaddr + p_filesz:
                continue
            file_offset = p_offset + (entry - p_vaddr)
            if data[file_offset : file_offset + len(payload)] != payload:
                raise MaloraError(
                    f"entry point 0x{entry:x} does not begin with the expected payload"
                )
            return ElfCheck(entry=entry, payload_offset=file_offset)
    except struct.error:
        raise MaloraError("output ELF headers are malformed") from None

    raise MaloraError(f"entry point 0x{entry:x} is not inside a loadable segment")
