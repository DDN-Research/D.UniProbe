"""Робота з файлами прошивок: .bin / .hex / .elf -> сегменти (адреса, дані)."""
import os
from typing import List, Tuple

Segment = Tuple[int, bytes]


def file_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".hex", ".ihex"):
        return "hex"
    if ext in (".elf", ".axf", ".out"):
        return "elf"
    return "bin"


def load_segments(path: str, base: int = 0) -> List[Segment]:
    fmt = file_format(path)
    if fmt == "bin":
        with open(path, "rb") as f:
            return [(base, f.read())]
    if fmt == "hex":
        from intelhex import IntelHex
        ih = IntelHex(path)
        segs = []
        for start, end in ih.segments():
            segs.append((start, ih.tobinstr(start=start, end=end - 1)))
        return segs
    # ELF: завантажувані сегменти за фізичною адресою (LMA)
    from elftools.elf.elffile import ELFFile
    segs = []
    with open(path, "rb") as f:
        elf = ELFFile(f)
        for seg in elf.iter_segments():
            if seg["p_type"] == "PT_LOAD" and seg["p_filesz"] > 0:
                segs.append((seg["p_paddr"], seg.data()[: seg["p_filesz"]]))
    return segs


def save_data(path: str, addr: int, data: bytes) -> None:
    if file_format(path) == "hex":
        from intelhex import IntelHex
        ih = IntelHex()
        ih.frombytes(data, offset=addr)
        ih.write_hex_file(path)
    else:
        with open(path, "wb") as f:
            f.write(data)


def hexdump(addr: int, data: bytes, limit: int = 65536) -> str:
    out = []
    view = data[:limit]
    for off in range(0, len(view), 16):
        chunk = view[off:off + 16]
        hx = " ".join(f"{b:02X}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{addr + off:08X}  {hx:<47}  {asc}")
    if len(data) > limit:
        out.append(f"... показано {limit} з {len(data)} байт (решта - у файлі)")
    return "\n".join(out)


def parse_int(text: str) -> int:
    t = text.strip().lower().replace("_", "")
    mult = 1
    if t.endswith("k"):
        mult, t = 1024, t[:-1]
    elif t.endswith("m"):
        mult, t = 1024 * 1024, t[:-1]
    return int(t, 0) * mult
