"""D.UNI Programmer - програма для роботи з флешем мікроконтролерів через D.UNI Probe.
ARM (SWD): STM32, RP2040 та інші Cortex-M (pyOCD).  ESP32/ESP8266 (UART): esptool.
Запуск: run.bat (Windows) або  python duni_programmer.py
"""
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duni import APP_VERSION                                    # noqa: E402
from duni.fileutil import hexdump, parse_int, save_data, file_format  # noqa: E402
from duni.arm_backend import ArmBackend                         # noqa: E402
from duni.esp_backend import EspBackend, list_ports             # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(APP_DIR, "duni_settings.json")
FREQS = {"100 kHz": 100_000, "500 kHz": 500_000, "1 MHz": 1_000_000, "4 MHz": 4_000_000, "10 MHz": 10_000_000}
DEFAULT_BASE = {"rp2040": "0x10000000"}


class QueueLogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__(logging.INFO)
        self.app = app
        self.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    def emit(self, record):
        self.app.post("log", self.format(record))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"D.UNI Programmer v{APP_VERSION}")
        self.geometry("1060x780")
        self.minsize(900, 640)
        self.q = queue.Queue()
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.busy = 0
        self.arm = ArmBackend()
        self.esp = EspBackend()
        self.last_read = None  # (addr, bytes)
        self.cfg = self._load_cfg()
        self._build()
        logging.getLogger().addHandler(QueueLogHandler(self))
        logging.getLogger().setLevel(logging.INFO)
        self.after(50, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log(f"D.UNI Programmer v{APP_VERSION}. Python {sys.version.split()[0]}")
        self.refresh_devices()
        self.run("Завантаження списку цілей", ArmBackend.list_targets, self._set_targets)

    # ------------------------------------------------------------ settings
    def _load_cfg(self):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cfg(self):
        keys = ["target", "freq", "mode", "arm_file", "arm_base", "erase", "rd_addr", "rd_size",
                "esp_chip", "esp_baud"]
        data = {k: getattr(self, "v_" + k).get() for k in keys}
        data["esp_rows"] = [(r[0].get(), r[1].get(), r[2].get()) for r in self.esp_rows]
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _var(self, name, default):
        v = tk.StringVar(value=self.cfg.get(name, default))
        setattr(self, "v_" + name, v)
        return v

    # ------------------------------------------------------------ UI
    def _build(self):
        pad = {"padx": 4, "pady": 3}
        top = ttk.LabelFrame(self, text="Пристрій D.UNI Probe")
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Пробник (SWD/JTAG):").grid(row=0, column=0, sticky="e", **pad)
        self.cb_probe = ttk.Combobox(top, width=48, state="readonly")
        self.cb_probe.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(top, text="COM-порт (UART):").grid(row=0, column=2, sticky="e", **pad)
        self.cb_port = ttk.Combobox(top, width=40, state="readonly")
        self.cb_port.grid(row=0, column=3, sticky="w", **pad)
        ttk.Button(top, text="Оновити", command=self.refresh_devices).grid(row=0, column=4, **pad)
        self.lbl_state = ttk.Label(top, text="Ціль: не підключена", foreground="gray")
        self.lbl_state.grid(row=1, column=0, columnspan=5, sticky="w", **pad)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6)
        self.tab_arm = ttk.Frame(nb)
        self.tab_esp = ttk.Frame(nb)
        self.tab_hex = ttk.Frame(nb)
        nb.add(self.tab_arm, text="  ARM / SWD  (STM32, RP2040, ...)  ")
        nb.add(self.tab_esp, text="  ESP32 / UART  ")
        nb.add(self.tab_hex, text="  Пам'ять (HEX)  ")
        self.nb = nb
        self._build_arm()
        self._build_esp()
        self._build_hex()

        bottom = ttk.Frame(self)
        bottom.pack(fill="both", padx=6, pady=4)
        pr = ttk.Frame(bottom)
        pr.pack(fill="x")
        self.pb = ttk.Progressbar(pr, maximum=1000)
        self.pb.pack(side="left", fill="x", expand=True)
        self.lbl_busy = ttk.Label(pr, text="Готово", width=36)
        self.lbl_busy.pack(side="left", padx=6)
        ttk.Button(pr, text="Очистити лог", command=lambda: self.txt_log.delete("1.0", "end")).pack(side="left")
        self.txt_log = ScrolledText(bottom, height=11, font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.tag_config("err", foreground="red")
        self.txt_log.tag_config("ok", foreground="green")

    def _build_arm(self):
        f = self.tab_arm
        pad = {"padx": 4, "pady": 3}
        c = ttk.LabelFrame(f, text="Підключення до цілі")
        c.pack(fill="x", padx=4, pady=4)
        ttk.Label(c, text="Ціль:").grid(row=0, column=0, sticky="e", **pad)
        self.cb_target = ttk.Combobox(c, width=22, textvariable=self._var("target", "stm32f103rc"))
        self.cb_target.grid(row=0, column=1, **pad)
        self.cb_target.bind("<<ComboboxSelected>>", self._target_changed)
        ttk.Label(c, text="Частота:").grid(row=0, column=2, sticky="e", **pad)
        ttk.Combobox(c, width=9, state="readonly", values=list(FREQS), textvariable=self._var("freq", "4 MHz")).grid(row=0, column=3, **pad)
        ttk.Label(c, text="Режим:").grid(row=0, column=4, sticky="e", **pad)
        ttk.Combobox(c, width=12, state="readonly", values=["halt", "under-reset", "pre-reset", "attach"],
                     textvariable=self._var("mode", "halt")).grid(row=0, column=5, **pad)
        b = ttk.Frame(c)
        b.grid(row=1, column=0, columnspan=8, sticky="w")
        for txt, cmd in (("Підключити", self.arm_connect), ("Відключити", self.arm_disconnect),
                         ("Інформація", self.arm_info), ("Reset", lambda: self.arm_ctl("reset")),
                         ("Reset+Halt", lambda: self.arm_ctl("reset_halt")), ("Halt", lambda: self.arm_ctl("halt")),
                         ("Run", lambda: self.arm_ctl("resume"))):
            ttk.Button(b, text=txt, command=cmd).pack(side="left", padx=3, pady=3)
        ttk.Label(c, text="Немає вашого чипа? Pack:").grid(row=0, column=6, sticky="e", **pad)
        pk = ttk.Frame(c)
        pk.grid(row=0, column=7, sticky="w")
        self.v_pack = tk.StringVar(value="stm32f103c8")
        ttk.Entry(pk, width=14, textvariable=self.v_pack).pack(side="left")
        ttk.Button(pk, text="Встановити", command=self.arm_pack_install).pack(side="left", padx=3)

        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=4)
        mm = ttk.LabelFrame(mid, text="Карта пам'яті (клік - підставити адресу)")
        mm.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.tv_mm = ttk.Treeview(mm, columns=("start", "end", "size", "type"), height=6)
        for col, w, t in (("#0", 120, "Регіон"), ("start", 100, "Початок"), ("end", 100, "Кінець"),
                          ("size", 90, "Розмір"), ("type", 60, "Тип")):
            self.tv_mm.heading(col, text=t)
            self.tv_mm.column(col, width=w, stretch=col == "#0")
        self.tv_mm.pack(fill="both", expand=True)
        self.tv_mm.bind("<<TreeviewSelect>>", self._mm_select)

        right = ttk.Frame(mid)
        right.pack(side="left", fill="both", expand=True)
        p = ttk.LabelFrame(right, text="Програмування (.bin / .hex / .elf)")
        p.pack(fill="x")
        ttk.Label(p, text="Файл:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(p, width=46, textvariable=self._var("arm_file", "")).grid(row=0, column=1, columnspan=3, sticky="we", **pad)
        ttk.Button(p, text="...", width=3, command=self._browse_arm).grid(row=0, column=4, **pad)
        ttk.Label(p, text="Адреса (для .bin):").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(p, width=12, textvariable=self._var("arm_base", "0x08000000")).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(p, text="Стирання:").grid(row=1, column=2, sticky="e", **pad)
        ttk.Combobox(p, width=8, state="readonly", values=["auto", "sector", "chip"],
                     textvariable=self._var("erase", "sector")).grid(row=1, column=3, sticky="w", **pad)
        self.v_verify = tk.BooleanVar(value=True)
        self.v_reset_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text="Verify після запису", variable=self.v_verify).grid(row=2, column=1, sticky="w", **pad)
        ttk.Checkbutton(p, text="Reset і запуск", variable=self.v_reset_after).grid(row=2, column=2, columnspan=2, sticky="w", **pad)
        bb = ttk.Frame(p)
        bb.grid(row=3, column=0, columnspan=5, sticky="w")
        ttk.Button(bb, text="ЗАПИСАТИ", command=self.arm_program).pack(side="left", padx=3, pady=3)
        ttk.Button(bb, text="Перевірити (Verify)", command=self.arm_verify).pack(side="left", padx=3)

        r = ttk.LabelFrame(right, text="Флеш / пам'ять")
        r.pack(fill="x", pady=4)
        ttk.Label(r, text="Адреса:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(r, width=12, textvariable=self._var("rd_addr", "0x08000000")).grid(row=0, column=1, **pad)
        ttk.Label(r, text="Розмір:").grid(row=0, column=2, sticky="e", **pad)
        ttk.Entry(r, width=10, textvariable=self._var("rd_size", "0x1000")).grid(row=0, column=3, **pad)
        ttk.Label(r, text="(напр. 0x1000, 64k, 1m)").grid(row=0, column=4, sticky="w", **pad)
        rb = ttk.Frame(r)
        rb.grid(row=1, column=0, columnspan=5, sticky="w")
        for txt, cmd in (("Прочитати", self.arm_read), ("Прочитати у файл...", self.arm_read_file),
                         ("Перевірка на чистоту", self.arm_blank), ("Стерти діапазон", self.arm_erase_range),
                         ("Стерти ВЕСЬ чип", self.arm_erase_chip)):
            ttk.Button(rb, text=txt, command=cmd).pack(side="left", padx=3, pady=3)

    def _build_esp(self):
        f = self.tab_esp
        pad = {"padx": 4, "pady": 3}
        c = ttk.LabelFrame(f, text="Параметри (порт обирається вгорі: COM-порт D.UNI Probe)")
        c.pack(fill="x", padx=4, pady=4)
        ttk.Label(c, text="Чип:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Combobox(c, width=10, state="readonly", textvariable=self._var("esp_chip", "auto"),
                     values=["auto", "esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3", "esp32c6", "esp32h2", "esp8266"]).grid(row=0, column=1, **pad)
        ttk.Label(c, text="Швидкість:").grid(row=0, column=2, sticky="e", **pad)
        ttk.Combobox(c, width=8, values=["115200", "230400", "460800", "921600"],
                     textvariable=self._var("esp_baud", "460800")).grid(row=0, column=3, **pad)
        ttk.Button(c, text="Інформація про чип", command=self.esp_info).grid(row=0, column=4, **pad)
        ttk.Button(c, text="Стерти ВЕСЬ флеш", command=self.esp_erase_all).grid(row=0, column=5, **pad)

        w = ttk.LabelFrame(f, text="Запис (ESP32: bootloader 0x1000; S2/S3/C3/C6/H2: bootloader 0x0; partitions 0x8000; app 0x10000)")
        w.pack(fill="x", padx=4, pady=4)
        defaults = [("1", "0x1000", ""), ("1", "0x8000", ""), ("1", "0x10000", ""), ("0", "0x0", "")]
        saved = self.cfg.get("esp_rows", defaults)
        self.esp_rows = []
        for i in range(4):
            en, ad, fl = saved[i] if i < len(saved) else defaults[i]
            ve, va, vf = tk.StringVar(value=en), tk.StringVar(value=ad), tk.StringVar(value=fl)
            ttk.Checkbutton(w, variable=ve, onvalue="1", offvalue="0").grid(row=i, column=0, **pad)
            ttk.Entry(w, width=10, textvariable=va).grid(row=i, column=1, **pad)
            ttk.Entry(w, width=70, textvariable=vf).grid(row=i, column=2, sticky="we", **pad)
            ttk.Button(w, text="...", width=3, command=lambda v=vf: self._browse_into(v, [("Binary", "*.bin"), ("All", "*.*")])).grid(row=i, column=3, **pad)
            self.esp_rows.append((ve, va, vf))
        self.v_esp_erase_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(w, text="Стерти весь флеш перед записом", variable=self.v_esp_erase_all).grid(row=4, column=2, sticky="w", **pad)
        wb = ttk.Frame(w)
        wb.grid(row=5, column=0, columnspan=4, sticky="w")
        ttk.Button(wb, text="ЗАПИСАТИ (з перевіркою MD5)", command=self.esp_write).pack(side="left", padx=3, pady=3)
        ttk.Button(wb, text="Перевірити (Verify)", command=self.esp_verify).pack(side="left", padx=3)

        r = ttk.LabelFrame(f, text="Читання / стирання регіону")
        r.pack(fill="x", padx=4, pady=4)
        self.v_esp_addr = tk.StringVar(value="0x0")
        self.v_esp_size = tk.StringVar(value="0x400000")
        ttk.Label(r, text="Адреса:").grid(row=0, column=0, **pad)
        ttk.Entry(r, width=12, textvariable=self.v_esp_addr).grid(row=0, column=1, **pad)
        ttk.Label(r, text="Розмір:").grid(row=0, column=2, **pad)
        ttk.Entry(r, width=12, textvariable=self.v_esp_size).grid(row=0, column=3, **pad)
        ttk.Button(r, text="Прочитати у файл...", command=self.esp_read).grid(row=0, column=4, **pad)
        ttk.Button(r, text="Стерти регіон", command=self.esp_erase_region).grid(row=0, column=5, **pad)
        ttk.Label(f, text="Перехід ESP32 у режим завантаження - автоматично (лінії EN/IO0 D.UNI Probe, роз'єм J3).",
                  foreground="gray").pack(anchor="w", padx=8)

    def _build_hex(self):
        f = self.tab_hex
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=3)
        ttk.Button(bar, text="Зберегти у файл (.bin/.hex)...", command=self.save_last_read).pack(side="left", padx=4)
        self.lbl_hex = ttk.Label(bar, text="Немає даних. Прочитайте пам'ять на вкладці ARM.")
        self.lbl_hex.pack(side="left", padx=8)
        self.txt_hex = ScrolledText(f, font=("Consolas", 10))
        self.txt_hex.pack(fill="both", expand=True)

    # ------------------------------------------------------------ infra
    def post(self, kind, *args):
        self.q.put((kind, args))

    def log(self, text, tag=None):
        self.post("log", text, tag)

    def _poll(self):
        try:
            while True:
                kind, args = self.q.get_nowait()
                if kind == "log":
                    text = args[0]
                    tag = args[1] if len(args) > 1 else None
                    if tag is None and (text.startswith("ERROR") or "ПОМИЛКА" in text):
                        tag = "err"
                    self.txt_log.insert("end", time.strftime("%H:%M:%S ") + text + "\n", tag)
                    self.txt_log.see("end")
                elif kind == "progress":
                    self.pb["value"] = max(0, min(1000, int(args[0] * 1000)))
                elif kind == "call":
                    args[0](*args[1:])
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def progress(self, frac):
        self.post("progress", frac)

    def run(self, title, fn, on_done=None, *fargs):
        self.busy += 1  # операції стають у чергу і виконуються по одній
        self.lbl_busy.config(text=title + "...")
        self.pb["value"] = 0
        self.log(f"--- {title}")
        t0 = time.time()

        def job():
            try:
                res = fn(*fargs)
                self.post("call", self._job_done, title, True, time.time() - t0, on_done, res)
            except Exception as e:  # noqa: BLE001
                logging.getLogger("duni").debug("trace", exc_info=True)
                self.post("call", self._job_done, title, False, time.time() - t0, None, e)
        self.worker.submit(job)

    def _job_done(self, title, ok, dt, on_done, res):
        self.busy -= 1
        if self.busy == 0:
            self.lbl_busy.config(text="Готово" if ok else "Помилка")
        if ok:
            self.pb["value"] = 1000
            self.log(f"{title}: виконано за {dt:.1f} с", "ok")
            if on_done:
                on_done(res)
        else:
            self.log(f"ПОМИЛКА ({title}): {res}", "err")

    def report_callback_exception(self, exc, val, tb):
        self.log(f"ПОМИЛКА: {val}", "err")

    def _on_close(self):
        self._save_cfg()
        try:
            self.arm.disconnect()
        except Exception:
            pass
        self.destroy()
        os._exit(0)

    # ------------------------------------------------------------ helpers
    def _browse_arm(self):
        self._browse_into(self.v_arm_file, [("Firmware", "*.hex *.bin *.elf *.axf"), ("All", "*.*")])

    def _browse_into(self, var, types):
        p = filedialog.askopenfilename(filetypes=types)
        if p:
            var.set(p)

    def _set_targets(self, names):
        self.cb_target["values"] = names
        self.log(f"Доступно цілей pyOCD: {len(names)} (STM32 без вбудованої підтримки - через кнопку 'Встановити' pack)")

    def _target_changed(self, *_):
        t = self.v_target.get().lower()
        for k, v in DEFAULT_BASE.items():
            if t.startswith(k):
                self.v_arm_base.set(v)
                self.v_rd_addr.set(v)
                return
        if t.startswith("stm32"):
            self.v_arm_base.set("0x08000000")
            self.v_rd_addr.set("0x08000000")

    def _mm_select(self, *_):
        sel = self.tv_mm.selection()
        if sel:
            vals = self.tv_mm.item(sel[0], "values")
            self.v_rd_addr.set(vals[0])
            self.v_rd_size.set(hex(parse_int(vals[2])))

    def _probe_uid(self):
        i = self.cb_probe.current()
        return self.probes[i][0] if 0 <= i < len(self.probes) else None

    def _port(self):
        i = self.cb_port.current()
        return self.ports[i][0] if 0 <= i < len(self.ports) else None

    def _confirm(self, text):
        return messagebox.askyesno("Підтвердження", text)

    # ------------------------------------------------------------ device list
    def refresh_devices(self):
        def work():
            return ArmBackend.list_probes(), list_ports()

        def done(res):
            self.probes, self.ports = res
            self.cb_probe["values"] = [p[1] for p in self.probes] or ["(пробник не знайдено)"]
            self.cb_probe.current(0)
            self.cb_port["values"] = [p[1] for p in self.ports] or ["(COM-портів немає)"]
            self.cb_port.current(0)
            self.log(f"Знайдено пробників: {len(self.probes)}, COM-портів: {len(self.ports)}")
        self.probes, self.ports = [], []
        self.run("Пошук пристроїв", work, done)

    # ------------------------------------------------------------ ARM actions
    def arm_connect(self):
        def done(info):
            self.lbl_state.config(text="Ціль: ПІДКЛЮЧЕНА - " + info.splitlines()[1], foreground="green")
            self.log(info)
            self.run("Карта пам'яті", self.arm.memory_map, self._show_mm)
        self.run("Підключення", self.arm.connect, done, self._probe_uid(), self.v_target.get().strip().lower(),
                 FREQS[self.v_freq.get()], self.v_mode.get())

    def _show_mm(self, regions):
        self.tv_mm.delete(*self.tv_mm.get_children())
        for name, start, end, length, is_flash in regions:
            self.tv_mm.insert("", "end", text=name, values=(f"0x{start:08X}", f"0x{end:08X}", f"{length:#x}",
                                                            "FLASH" if is_flash else "RAM/інше"))

    def arm_disconnect(self):
        def done(_):
            self.lbl_state.config(text="Ціль: не підключена", foreground="gray")
        self.run("Відключення", self.arm.disconnect, done)

    def arm_info(self):
        self.run("Інформація", self.arm.info, lambda s: self.log(s))

    def arm_ctl(self, what):
        fn = {"reset": lambda: self.arm.reset(False), "reset_halt": lambda: self.arm.reset(True),
              "halt": self.arm.halt, "resume": self.arm.resume}[what]
        self.run(what, fn)

    def arm_pack_install(self):
        name = self.v_pack.get().strip()
        if not name:
            return

        def work():
            import subprocess
            cmd = [sys.executable, "-m", "pyocd", "pack", "install", name]
            self.log(" ".join(cmd) + "   (перший раз завантажується індекс CMSIS-Pack, це довго)")
            p = subprocess.run(cmd, capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in (p.stdout + p.stderr).splitlines():
                if line.strip():
                    self.log(line)
            if p.returncode:
                raise RuntimeError("pack install завершився з помилкою")
            return ArmBackend.list_targets()
        self.run(f"Встановлення pack {name}", work, self._set_targets)

    def arm_program(self):
        path = self.v_arm_file.get()
        if not os.path.isfile(path):
            messagebox.showerror("Файл", "Оберіть файл прошивки")
            return

        def done(res):
            if res:
                self.log(res[1], "ok" if res[0] else "err")
        self.run("Запис флешу", self.arm.program, done, path, parse_int(self.v_arm_base.get()),
                 self.v_erase.get(), self.v_verify.get(), self.v_reset_after.get(), self.progress)

    def arm_verify(self):
        path = self.v_arm_file.get()
        if not os.path.isfile(path):
            messagebox.showerror("Файл", "Оберіть файл прошивки")
            return
        self.run("Verify", self.arm.verify, lambda r: self.log(r[1], "ok" if r[0] else "err"),
                 path, parse_int(self.v_arm_base.get()), self.progress)

    def _rd(self):
        return parse_int(self.v_rd_addr.get()), parse_int(self.v_rd_size.get())

    def arm_read(self):
        addr, size = self._rd()

        def done(data):
            self.last_read = (addr, data)
            self.txt_hex.delete("1.0", "end")
            self.txt_hex.insert("1.0", hexdump(addr, data))
            self.lbl_hex.config(text=f"0x{addr:08X} .. 0x{addr + len(data) - 1:08X}  ({len(data)} байт)")
            self.nb.select(self.tab_hex)
        self.run("Читання пам'яті", self.arm.read, done, addr, size, self.progress)

    def arm_read_file(self):
        addr, size = self._rd()
        path = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("Binary", "*.bin"), ("Intel HEX", "*.hex")])
        if not path:
            return

        def work():
            data = self.arm.read(addr, size, self.progress)
            save_data(path, addr, data)
            self.last_read = (addr, data)
            return path
        self.run("Читання у файл", work, lambda p: self.log(f"Збережено: {p}", "ok"))

    def arm_blank(self):
        addr, size = self._rd()
        self.run("Перевірка на чистоту", self.arm.blank_check, lambda r: self.log(r[1], "ok" if r[0] else "err"),
                 addr, size, self.progress)

    def arm_erase_range(self):
        addr, size = self._rd()
        if self._confirm(f"Стерти флеш 0x{addr:08X} .. 0x{addr + size - 1:08X}?"):
            self.run("Стирання діапазону", self.arm.erase_range, None, addr, size)

    def arm_erase_chip(self):
        if self._confirm("Стерти ВЕСЬ флеш мікроконтролера?"):
            self.run("Стирання чипа", self.arm.erase_chip)

    def save_last_read(self):
        if not self.last_read:
            return
        path = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("Binary", "*.bin"), ("Intel HEX", "*.hex")])
        if path:
            save_data(path, *self.last_read)
            self.log(f"Збережено: {path} ({file_format(path)})", "ok")

    # ------------------------------------------------------------ ESP actions
    def _esp(self):
        return self._port(), int(self.v_esp_baud.get()), self.v_esp_chip.get()

    def _esp_pairs(self):
        pairs = []
        for en, ad, fl in self.esp_rows:
            if en.get() == "1" and fl.get().strip():
                if not os.path.isfile(fl.get()):
                    raise RuntimeError(f"Файл не знайдено: {fl.get()}")
                pairs.append((parse_int(ad.get()), fl.get()))
        if not pairs:
            raise RuntimeError("Не вибрано жодного файлу для запису")
        return pairs

    def esp_info(self):
        self.run("ESP: інформація", self.esp.info, None, *self._esp(), self.log, self.progress)

    def esp_erase_all(self):
        if self._confirm("Стерти ВЕСЬ флеш ESP?"):
            self.run("ESP: стирання", self.esp.erase_all, None, *self._esp(), self.log, self.progress)

    def esp_write(self):
        try:
            pairs = self._esp_pairs()
        except RuntimeError as e:
            messagebox.showerror("Запис", str(e))
            return
        self.run("ESP: запис", self.esp.write, None, *self._esp(), pairs, self.v_esp_erase_all.get(), self.log, self.progress)

    def esp_verify(self):
        try:
            pairs = self._esp_pairs()
        except RuntimeError as e:
            messagebox.showerror("Verify", str(e))
            return
        self.run("ESP: verify", self.esp.verify, None, *self._esp(), pairs, self.log, self.progress)

    def esp_read(self):
        path = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("Binary", "*.bin")])
        if path:
            self.run("ESP: читання", self.esp.read, None, *self._esp(), parse_int(self.v_esp_addr.get()),
                     parse_int(self.v_esp_size.get()), path, self.log, self.progress)

    def esp_erase_region(self):
        a, s = parse_int(self.v_esp_addr.get()), parse_int(self.v_esp_size.get())
        if self._confirm(f"Стерти ESP флеш 0x{a:X} .. 0x{a + s - 1:X}?"):
            self.run("ESP: стирання регіону", self.esp.erase_region, None, *self._esp(), a, s, self.log, self.progress)


if __name__ == "__main__":
    App().mainloop()
