# D.UNI Probe v1.1 — прошивка для Raspberry Pi Pico (RP2040)

Програматор-дебагер **CMSIS-DAP v2** (USB, без драйверів у Windows 10/11).
Основа: офіційна Raspberry Pi **Debugprobe** (MIT) + доробки D.UNI.

| Можливість | Стан |
|---|---|
| SWD (PIO, до ~25 МГц) — RP2040/RP2350, STM32, EFR32, SAM, nRF… | ✅ |
| nRESET цілі (GP1) | ✅ |
| **JTAG** (CMSIS-DAP JTAG port, GP2/3/6/7/8) — класичний ESP32 та інші JTAG-цілі | ✅ нове |
| USB-UART міст (COM-порт, GP4/GP5), автоматична швидкість | ✅ |
| **Автовхід ESP32 у bootloader** (емуляція DTR/RTS esptool -> EN/IO0) | ✅ нове |
| **STM32**: SWD, апаратний NRST (connect under reset), OpenOCD / VS Code / STM32CubeIDE | ✅ v1.1 |
| Індикація: **LED на Pico (GP25) блимає 1 раз/с** — прошивка працює; GP15 — DAP running | ✅ v1.1 |

## 1. Встановлення прошивки
1. Затисніть **BOOTSEL** на Pico, вставте USB -> з'явиться диск `RPI-RP2`.
2. Скопіюйте `bin/duni_probe_v1.uf2` на цей диск. Pico перезавантажиться.
3. У Диспетчері пристроїв: **"D.UNI Probe v1.1 (CMSIS-DAP)"** + **COM-порт**.
   VID:PID = 2E8A:000C (як у Debugprobe), тож OpenOCD, probe-rs, pyOCD і розширення
   Raspberry Pi Pico розпізнають пристрій автоматично.

## 1a. Світлодіод на Pico (GP25)
| Що бачите | Значення |
|---|---|
| Блимає **1 раз на секунду** | Прошивка працює, USB підключено до ПК — норма |
| Блимає часто (5 разів/с) | Прошивка працює, але ПК не розпізнав USB (кабель лише для живлення, зарядка) |
| Не світиться / світиться постійно | Прошивка не запустилась — перепрошийте UF2 |

## 2. Розподіл пінів (див. KiCAD/Ver 1)
| Pico | Функція | RP2040 (ціль) | ESP32 (ціль) |
|---|---|---|---|
| GP2 | SWCLK / TCK | SWCLK | MTCK = IO13 |
| GP3 | SWDIO / TMS | SWDIO | MTMS = IO14 |
| GP6 | TDI | — | MTDI = IO12 |
| GP7 | TDO / SWO | — | MTDO = IO15 |
| GP8 | nTRST | — | — |
| GP1 | nRESET | RUN | EN (для JTAG, опційно) |
| GP4 | UART TX | GP1 (UART0 RX) | U0RXD (GPIO3) |
| GP5 | UART RX | GP0 (UART0 TX) | U0TXD (GPIO1) |
| GP10 | ESP EN | — | EN |
| GP11 | ESP IO0 | — | GPIO0 |
| GND | GND | GND | GND — **обов'язково** |

Цілі — тільки 3.3 В (у v1 немає перетворювачів рівнів).

## 3. RP2040 як ціль (відладка у VS Code)
1. Розширення: **Raspberry Pi Pico**, **Cortex-Debug**.
2. Створіть проєкт (New C/C++ Project, board Pico).
3. Скопіюйте `vscode-examples/rp2040-target/.vscode/launch.json` у `.vscode/` проєкту
   (або використайте вбудовану конфігурацію "Pico Debug (Cortex-Debug)" — вона теж працює).
4. **F5** — збирання, прошивка, зупинка на `main()`.

Без VS Code (тільки прошити):
```
openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg -c "adapter speed 5000" -c "program app.elf verify reset exit"
probe-rs download --chip RP2040 app.elf
```

## 4. ESP32 як ціль
### 4.1 Прошивка через UART (усі ESP32, у т.ч. S2/S3/C3/C6)
З'єднайте J3: TX->U0RXD, RX<-U0TXD, EN, IO0, GND.
Прошивка сама перезапускає ESP32 у режим завантаження — **кнопки BOOT/EN натискати не треба**:
```
idf.py -p COM5 flash monitor
esptool.py --port COM5 --baud 921600 write_flash 0x0 firmware.bin
```
Працює також з Arduino IDE і PlatformIO (стандартний режим reset "default_reset").

### 4.2 Відладка класичного ESP32 через JTAG
1. Розширення **ESP-IDF** (Espressif), встановіть ESP-IDF v5.x (там openocd-esp32 з підтримкою cmsis-dap).
2. З'єднайте GP2->IO13, GP3->IO14, GP6->IO12, GP7->IO15, GND (див. таблицю).
   Увага: IO12 (MTDI) — strapping-пін напруги флешу. Якщо під час скидання на ньому 1, ESP32 вибере 1.8 В
   і не завантажиться. Як і з ESP-Prog, для модулів із 3.3 В флешем (WROOM, більшість DevKit) один раз виконайте:
   `espefuse.py --port COM5 set_flash_voltage 3.3V` (незворотно, але безпечно для 3.3 В модулів).
3. Скопіюйте `vscode-examples/esp32-target/.vscode/*` у проєкт, вкажіть свій COM-порт.
4. **F5** -> "ESP32 via D.UNI Probe (JTAG)".

Перевірка з командного рядка (ESP-IDF terminal):
```
openocd -f interface/cmsis-dap.cfg -c "adapter speed 1000" -f target/esp32.cfg
```
JTAG у D.UNI v1 програмний (bit-bang): реальна частота ~0.3–1 МГц. Для відладки достатньо;
великі прошивки зручніше шити через UART (п. 4.1).

ESP32-S3/C3/C6/H2 мають вбудований USB-JTAG — їх зручніше відлагоджувати напряму по їх USB.

## 4a. STM32 як ціль
### Підключення
| D.UNI | STM32 |
|---|---|
| GP2 SWCLK (J1-4 / J2-2) | SWCLK (PA14) |
| GP3 SWDIO (J1-2 / J2-3) | SWDIO (PA13) |
| GP1 nRESET (J1-10 / J2-6) | NRST — бажано, обов'язково для "connect under reset" |
| GND | GND |
| 3V3 (JP1) | 3.3 В, якщо плата не має свого живлення |

Готові файли — у папці `stm32\`: `duni_stm32.cfg` (конфіг OpenOCD, змініть рядок `target/stm32xxx.cfg`
під свою серію) та `flash_stm32.bat` (прошивка без IDE).

### Прошивка без IDE
```
stm32\flash_stm32.bat firmware.elf
openocd -f stm32\duni_stm32.cfg -c "program firmware.hex verify reset exit"
openocd -f stm32\duni_stm32.cfg -c "program firmware.bin 0x08000000 verify reset exit"
```
Альтернативи: `pyocd flash -t stm32f103c8 firmware.hex`, `probe-rs download --chip STM32F103C8 firmware.elf`.

> **STM32CubeProgrammer з D.UNI не працює** — він підтримує лише фірмовий ST-LINK (закритий протокол).
> Замість нього — OpenOCD (вище), pyOCD або probe-rs: вони вміють стирати, шити, читати флеш і option bytes.

### VS Code
1. Розширення: **Cortex-Debug** (+ **STM32Cube for VS Code** від ST — для створення проєкту з CubeMX).
2. Проєкт: STM32CubeMX -> Project Manager -> Toolchain **CMake** -> Generate.
3. Скопіюйте `vscode-examples/stm32-target/.vscode/` у проєкт, змініть у `duni_stm32.cfg` серію чипа,
   у `launch.json` — `executable`, `device`, `svdFile` (SVD є в STM32CubeIDE/CubeCLT або на st.com).
4. Компілятор: STM32CubeCLT або ARM GCC з розширення Pico (`"cortex-debug.armToolchainPath"` у settings.json).
5. **F5** — прошивка і зупинка на `main()`.

### STM32CubeIDE
**Варіант A — вбудований OpenOCD CubeIDE:**
1. Run -> Debug Configurations -> STM32 C/C++ Application -> ваш проєкт -> вкладка **Debugger**.
2. Debug probe: **ST-LINK (OpenOCD)**.
3. Configuration script: **User Defined** -> вкажіть `stm32\duni_stm32.cfg`.
4. Reset behaviour: *Connect under reset* (якщо підключено NRST і розкоментовано `reset_config` у cfg), інакше *Software system reset*.
5. Debug.

**Варіант B — якщо CubeIDE пише про невідомий адаптер cmsis-dap** (OpenOCD від ST зібраний без нього):
1. Запустіть зовнішній OpenOCD (з розширення Pico або xPack OpenOCD):
   `openocd -f stm32\duni_stm32.cfg` — він слухає GDB на порту 3333.
2. У CubeIDE -> Debugger: Debug probe **ST-LINK (OpenOCD)**, GDB Connection Settings ->
   **Connect to remote GDB server**, Host `localhost`, Port `3333`.
3. Debug — CubeIDE сам завантажить прошивку через GDB.

## 5. Збирання прошивки з вихідного коду
Потрібно: Pico SDK **2.3.0**, ARM GCC, CMake (усе ставить розширення Raspberry Pi Pico).
- VS Code: Raspberry Pi Pico -> **Import Project** -> папка `source`, SDK 2.3.0 -> Compile.
- Або командний рядок:
```
cd source
mkdir build && cd build
cmake -DPICO_SDK_PATH=<шлях>/pico-sdk -DPICO_BOARD=pico ..
cmake --build .
```
Результат: `build/duni_probe_v1.uf2`.

### Що змінено відносно Debugprobe
- `include/board_duni_config.h` — пінмап D.UNI (новий файл).
- `include/DAP_config.h` — `DAP_JTAG 1`, реалізація пінів JTAG (bit-bang через SIO), перемикання PIO(SWD) <-> GPIO(JTAG).
- `src/sw_dp_pio.c` — SWJ_Sequence для JTAG-режиму.
- `src/cdc_uart.c` — емуляція автоскидання ESP32 (DTR/RTS -> EN/IO0), UART-міст не зупиняється при DTR=0.
- `CMakeLists.txt` — збірка `duni_probe_v1` для плати pico.
- `src/duni.c`, `src/duni.h` (v1.1) — блимання LED GP25 (1 Гц), ініціалізація лінії nRESET
  (у Debugprobe для Pico вона не ініціалізувалась, тож апаратний reset цілі не працював).

Зібрано та скомпільовано без попереджень; на реальному залізі ще **не тестувалося** —
першим тестом перевірте SWD на другому Pico, потім ESP32 через UART, потім JTAG.
