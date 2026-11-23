"""ESP32 / ESP8266 через UART-міст D.UNI Probe (esptool).
Прошивка D.UNI сама керує EN/IO0 (емуляція DTR/RTS), кнопки натискати не треба."""
import contextlib
import io
import re
from typing import Callable, List, Optional, Tuple

DUNI_VID, DUNI_PID = 0x2E8A, 0x000C
_PCT = re.compile(r"\((\d+)\s?%\)")


def list_ports() -> List[Tuple[str, str]]:
    from serial.tools import list_ports
    res = []
    for p in list_ports.comports():
        mark = "  <- D.UNI Probe" if (p.vid, p.pid) == (DUNI_VID, DUNI_PID) else ""
        res.append((p.device, f"{p.device}  {p.description}{mark}"))
    # порт D.UNI першим
    res.sort(key=lambda x: "D.UNI" not in x[1])
    return res


class _Writer(io.TextIOBase):
    def __init__(self, log: Callable[[str], None], progress: Optional[Callable[[float], None]]):
        self.log, self.progress, self.buf = log, progress, ""

    def write(self, s):
        self.buf += s
        while True:
            idx = min([i for i in (self.buf.find("\n"), self.buf.find("\r")) if i >= 0], default=-1)
            if idx < 0:
                break
            line, self.buf = self.buf[:idx], self.buf[idx + 1:]
            m = _PCT.search(line)
            if m and self.progress:
                self.progress(int(m.group(1)) / 100.0)
            elif line.strip():
                self.log(line.rstrip())
        return len(s)

    def flush(self):
        if self.buf.strip():
            self.log(self.buf.rstrip())
        self.buf = ""


def run_esptool(args: List[str], log, progress=None):
    import esptool
    w = _Writer(log, progress)
    log("esptool " + " ".join(args))
    with contextlib.redirect_stdout(w), contextlib.redirect_stderr(w):
        try:
            esptool.main(args)
        except esptool.FatalError as e:
            raise RuntimeError(str(e))
        except SystemExit as e:
            if e.code not in (0, None):
                raise RuntimeError(f"esptool завершився з кодом {e.code}")
        finally:
            w.flush()


class EspBackend:
    def base(self, port, baud, chip):
        if not port:
            raise RuntimeError("Не обрано COM-порт")
        return ["--port", port, "--baud", str(baud), "--chip", chip or "auto"]

    def info(self, port, baud, chip, log, progress=None):
        run_esptool(self.base(port, baud, chip) + ["flash_id"], log, progress)

    def erase_all(self, port, baud, chip, log, progress=None):
        run_esptool(self.base(port, baud, chip) + ["erase_flash"], log, progress)

    def erase_region(self, port, baud, chip, addr, size, log, progress=None):
        if addr % 4096 or size % 4096:
            raise RuntimeError("Адреса і розмір мають бути кратні 4096 (0x1000)")
        run_esptool(self.base(port, baud, chip) + ["erase_region", hex(addr), hex(size)], log, progress)

    def read(self, port, baud, chip, addr, size, path, log, progress=None):
        run_esptool(self.base(port, baud, chip) + ["read_flash", hex(addr), hex(size), path], log, progress)

    def write(self, port, baud, chip, pairs, erase_all, log, progress=None):
        args = self.base(port, baud, chip) + ["write_flash"]
        if erase_all:
            args.append("--erase-all")
        for a, f in pairs:
            args += [hex(a), f]
        run_esptool(args, log, progress)  # esptool сам перевіряє MD5 після запису

    def verify(self, port, baud, chip, pairs, log, progress=None):
        args = self.base(port, baud, chip) + ["verify_flash"]
        for a, f in pairs:
            args += [hex(a), f]
        run_esptool(args, log, progress)
