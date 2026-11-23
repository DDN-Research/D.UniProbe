"""ARM Cortex-M (SWD) через D.UNI Probe (CMSIS-DAP) на базі pyOCD.
Підтримка: STM32 (усі серії, вбудовані або з CMSIS-Pack), RP2040, і будь-які
Cortex-M, для яких у pyOCD є target або CMSIS-Pack."""
import logging
from typing import Callable, List, Optional, Tuple

from .fileutil import load_segments, file_format

LOG = logging.getLogger("duni.arm")
Progress = Optional[Callable[[float], None]]

CPU_NAMES = {0xC20: "Cortex-M0", 0xC60: "Cortex-M0+", 0xC21: "Cortex-M1", 0xC23: "Cortex-M3",
             0xC24: "Cortex-M4", 0xC27: "Cortex-M7", 0xD20: "Cortex-M23", 0xD21: "Cortex-M33",
             0xD22: "Cortex-M55", 0xD23: "Cortex-M85"}

# STM32 DEV_ID -> (назва, адреса регістра розміру флешу)
STM32_DEV = {
    0x412: ("STM32F10x low-density", 0x1FFFF7E0), 0x410: ("STM32F10x medium-density", 0x1FFFF7E0),
    0x414: ("STM32F10x high-density", 0x1FFFF7E0), 0x430: ("STM32F10x XL-density", 0x1FFFF7E0),
    0x418: ("STM32F105/107", 0x1FFFF7E0), 0x420: ("STM32F100 value line", 0x1FFFF7E0),
    0x440: ("STM32F030x8/F05x", 0x1FFFF7CC), 0x444: ("STM32F03x", 0x1FFFF7CC),
    0x445: ("STM32F04x/F070x6", 0x1FFFF7CC), 0x448: ("STM32F07x", 0x1FFFF7CC), 0x442: ("STM32F09x", 0x1FFFF7CC),
    0x422: ("STM32F30x/F31x", 0x1FFFF7CC), 0x438: ("STM32F334", 0x1FFFF7CC), 0x439: ("STM32F301/F318", 0x1FFFF7CC),
    0x413: ("STM32F405/407/415/417", 0x1FFF7A22), 0x419: ("STM32F42x/F43x", 0x1FFF7A22),
    0x423: ("STM32F401xB/C", 0x1FFF7A22), 0x433: ("STM32F401xD/E", 0x1FFF7A22), 0x431: ("STM32F411", 0x1FFF7A22),
    0x441: ("STM32F412", 0x1FFF7A22), 0x421: ("STM32F446", 0x1FFF7A22), 0x434: ("STM32F469/479", 0x1FFF7A22),
    0x449: ("STM32F74x/75x", 0x1FF0F442), 0x451: ("STM32F76x/77x", 0x1FF0F442),
    0x466: ("STM32G03x/G04x", 0x1FFF75E0), 0x460: ("STM32G07x/G08x", 0x1FFF75E0), 0x467: ("STM32G0Bx/G0Cx", 0x1FFF75E0),
    0x468: ("STM32G431/441", 0x1FFF75E0), 0x469: ("STM32G47x/48x", 0x1FFF75E0), 0x479: ("STM32G491/4A1", 0x1FFF75E0),
    0x415: ("STM32L47x/L48x", 0x1FFF75E0), 0x435: ("STM32L43x/L44x", 0x1FFF75E0), 0x462: ("STM32L45x/L46x", 0x1FFF75E0),
    0x461: ("STM32L496/4A6", 0x1FFF75E0), 0x417: ("STM32L05x/L06x", 0x1FF8007C), 0x447: ("STM32L07x/L08x", 0x1FF8007C),
    0x457: ("STM32L01x/L02x", 0x1FF8007C), 0x416: ("STM32L1 cat.1", 0x1FF8004C),
    0x450: ("STM32H74x/H75x", 0x1FF1E880), 0x483: ("STM32H72x/H73x", 0x1FF1E880),
    0x453: ("STM32C011", 0x1FFF75A0), 0x443: ("STM32C031", 0x1FFF75A0),
    0x482: ("STM32U575/585", 0x0BFA07A0), 0x495: ("STM32WB55", 0x1FFF75E0),
}
STM32_IDCODE_ADDRS = (0xE0042000, 0x40015800, 0x5C001000, 0xE0044000)


class ArmBackend:
    def __init__(self):
        self.session = None

    # ---------- probes / targets ----------
    @staticmethod
    def list_probes() -> List[Tuple[str, str]]:
        from pyocd.core.helpers import ConnectHelper
        probes = ConnectHelper.get_all_connected_probes(blocking=False, print_wait_message=False)
        return [(p.unique_id, f"{p.product_name} [{p.unique_id}]") for p in probes]

    @staticmethod
    def list_targets() -> List[str]:
        from pyocd.target import TARGET
        names = set(TARGET.keys())
        try:
            from pyocd.target.pack.pack_target import ManagedPacks
            for dev in ManagedPacks.get_installed_targets():
                names.add(dev.part_number.lower())
        except Exception as e:  # cmsis-pack-manager може бути не встановлений
            LOG.debug("packs: %s", e)
        return sorted(names)

    @property
    def connected(self) -> bool:
        return self.session is not None and self.session.is_open

    @property
    def target(self):
        if not self.connected:
            raise RuntimeError("Ціль не підключена. Натисніть 'Підключити'.")
        return self.session.board.target

    def connect(self, probe_uid: Optional[str], target: str, freq_hz: int, mode: str) -> str:
        from pyocd.core.helpers import ConnectHelper
        self.disconnect()
        opts = {"frequency": freq_hz, "connect_mode": mode, "target_override": target,
                "resume_on_disconnect": False}
        sess = ConnectHelper.session_with_chosen_probe(unique_id=probe_uid or None, blocking=False,
                                                       return_first=True, auto_open=False, options=opts)
        if sess is None:
            raise RuntimeError("Пробник D.UNI не знайдено. Перевірте USB і драйвер.")
        sess.open()
        self.session = sess
        return self.info()

    def disconnect(self):
        if self.session is not None:
            try:
                self.session.close()
            finally:
                self.session = None

    # ---------- info ----------
    def info(self) -> str:
        t = self.target
        lines = [f"Пробник: {self.session.probe.product_name} ({self.session.probe.unique_id})",
                 f"Target (pyOCD): {t.part_number}"]
        try:
            dpidr = t.dp.dpidr
            lines.append(f"DP IDR: 0x{getattr(dpidr, 'idr', dpidr):08X}")
        except Exception:
            pass
        try:
            cpuid = t.read32(0xE000ED00)
            part = (cpuid >> 4) & 0xFFF
            lines.append(f"CPUID: 0x{cpuid:08X} -> {CPU_NAMES.get(part, 'невідоме ядро')} r{(cpuid >> 20) & 0xF}p{cpuid & 0xF}")
        except Exception as e:
            lines.append(f"CPUID: не прочитано ({e})")
        if t.part_number.lower().startswith("stm32"):
            lines += self._stm32_info(t)
        if t.part_number.lower().startswith("rp2040"):
            try:
                chip_id = t.read32(0x40000000)
                lines.append(f"RP2040 CHIP_ID: 0x{chip_id:08X} (ревізія B{chip_id >> 28})")
            except Exception:
                pass
        return "\n".join(lines)

    def _stm32_info(self, t) -> List[str]:
        for a in STM32_IDCODE_ADDRS:
            try:
                v = t.read32(a)
            except Exception:
                continue
            dev = v & 0xFFF
            if v not in (0, 0xFFFFFFFF) and dev in STM32_DEV:
                name, fs_addr = STM32_DEV[dev]
                res = [f"STM32 DEV_ID: 0x{dev:03X} ({name}), REV_ID: 0x{v >> 16:04X}"]
                try:
                    kb = t.read16(fs_addr)
                    res.append(f"Розмір флешу (з чипа): {kb} КБ")
                except Exception:
                    pass
                return res
        return ["STM32 DEV_ID: не визначено"]

    def memory_map(self):
        return [(r.name, r.start, r.end, r.length, r.is_flash) for r in self.target.get_memory_map()]

    # ---------- control ----------
    def reset(self, halt: bool = False):
        if halt:
            self.target.reset_and_halt()
        else:
            self.target.reset()

    def halt(self):
        self.target.halt()

    def resume(self):
        self.target.resume()

    # ---------- memory ----------
    def read(self, addr: int, size: int, progress: Progress = None) -> bytes:
        t = self.target
        out = bytearray()
        step = 4096
        for off in range(0, size, step):
            n = min(step, size - off)
            out += bytes(t.read_memory_block8(addr + off, n))
            if progress:
                progress((off + n) / size)
        return bytes(out)

    def program(self, path: str, base: int, erase: str, verify: bool, reset: bool, progress: Progress = None):
        from pyocd.flash.file_programmer import FileProgrammer
        fmt = file_format(path)
        kw = {"base_address": base} if fmt == "bin" else {}
        FileProgrammer(self.session, progress=progress, chip_erase=erase, no_reset=True).program(
            path, file_format=fmt, **kw)
        result = None
        if verify:
            result = self.verify(path, base, progress)
        if reset:
            self.target.reset()
        return result

    def verify(self, path: str, base: int, progress: Progress = None) -> Tuple[bool, str]:
        segs = load_segments(path, base)
        mm = self.target.get_memory_map()
        total = sum(len(d) for _, d in segs) or 1
        done = 0
        bad = 0
        first = None
        for addr, data in segs:
            region = mm.get_region_for_address(addr)
            if region is None:
                LOG.warning("Сегмент 0x%08X поза картою пам'яті - пропущено", addr)
                continue
            for off in range(0, len(data), 4096):
                chunk = data[off:off + 4096]
                got = bytes(self.target.read_memory_block8(addr + off, len(chunk)))
                if got != chunk:
                    for i, (a, b) in enumerate(zip(got, chunk)):
                        if a != b:
                            bad += 1
                            if first is None:
                                first = (addr + off + i, a, b)
                done += len(chunk)
                if progress:
                    progress(done / total)
        if bad == 0:
            return True, f"Verify OK: {done} байт збігаються"
        a, got, exp = first
        return False, f"Verify ПОМИЛКА: {bad} байт відрізняються, перша: 0x{a:08X} прочитано 0x{got:02X}, очікувалось 0x{exp:02X}"

    def erase_chip(self):
        from pyocd.flash.eraser import FlashEraser
        FlashEraser(self.session, FlashEraser.Mode.CHIP).erase()

    def erase_range(self, start: int, size: int):
        from pyocd.flash.eraser import FlashEraser
        FlashEraser(self.session, FlashEraser.Mode.SECTOR).erase([f"0x{start:x}+0x{size:x}"])

    def blank_check(self, start: int, size: int, progress: Progress = None) -> Tuple[bool, str]:
        data = self.read(start, size, progress)
        for erased in (0xFF, 0x00):
            if all(b == erased for b in data):
                return True, f"Чисто: {size} байт = 0x{erased:02X}"
        for i, b in enumerate(data):
            if b != 0xFF:
                return False, f"НЕ чисто: перший записаний байт 0x{start + i:08X} = 0x{b:02X}"
        return False, "НЕ чисто"
