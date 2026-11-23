# D.UNI Probe v1 — розподіл пінів (Raspberry Pi Pico, RP2040)

Живлення: USB Pico (VBUS 5 В -> стабілізатор Pico 3.3 В).
**v1 без перетворювачів рівнів: підключати тільки цілі на 3.3 В!**
Усі сигнальні лінії йдуть через послідовні резистори 33–470 Ом (захист).

| Pico pin | GPIO | Сигнал | Роз'єм | Призначення | Стандартна debugprobe |
|---|---|---|---|---|---|
| 4 | GP2 | SWCLK / TCK | J1-4, J2-2 | SWD clock / JTAG TCK | ✅ |
| 5 | GP3 | SWDIO / TMS | J1-2, J2-3 | SWD data / JTAG TMS | ✅ |
| 6 | GP4 | UART_TX | J2-9, J3-2 | UART міст (COM-порт) -> RX цілі | ✅ |
| 7 | GP5 | UART_RX | J2-10, J3-3 | UART міст <- TX цілі | ✅ |
| 2 | GP1 | nRESET | J1-10, J2-6 | Скидання цілі (pull-up 10k) | потрібна збірка з PROBE_PIN_RESET |
| 9 | GP6 | TDI | J1-8, J2-5 | JTAG TDI | власна прошивка |
| 10 | GP7 | TDO / SWO | J1-6, J2-4 | JTAG TDO / SWO trace | власна прошивка |
| 11 | GP8 | nTRST | J2-7 | JTAG reset | власна прошивка |
| 14 | GP10 | ESP_EN | J3-4 | ESP32 EN (reset) | власна прошивка |
| 15 | GP11 | ESP_IO0 | J3-5 | ESP32 GPIO0 (boot mode) | власна прошивка |
| 16 | GP12 | UPDI | J5-2 | AVR UPDI (ATtiny 0/1, AVR-Dx), резерв | — |
| 21,22,24,25 | GP16–19 | ISP MISO/RST/SCK/MOSI | J4 | AVR ISP (SPI0), резерв | — |
| 26,27 | GP20/21 | SBWTCK / SBWTDIO | J6 | TI MSP430 Spy-Bi-Wire, резерв | — |
| 31 | GP26 ADC0 | VTREF_SENSE | — | Вимір напруги цілі (дільник 1:2) | — |
| 20 | GP15 | LED_ACT | D1 | Індикатор активності | — |
| 1,12,17,19,29,32,34 | GP0,9,13,14,22,27,28 | AUX0–AUX6 | J7 | Резерв | — |

## Роз'єми
- **J1** — Cortex Debug 10-pin 1.27 мм (стандарт ARM: STM32, EFR32, nRF, SAM, RP2040…):
  1 VTref, 2 SWDIO/TMS, 3 GND, 4 SWCLK/TCK, 5 GND, 6 SWO/TDO, 7 key, 8 TDI, 9 GND, 10 nRESET
- **J2** — 1x10 2.54 мм: 1 VTref, 2 SWCLK/TCK, 3 SWDIO/TMS, 4 TDO/SWO, 5 TDI, 6 nRESET, 7 nTRST, 8 GND, 9 UART_TX, 10 UART_RX
- **J3** — ESP32 (UART boot): 1 GND, 2 TX -> U0RXD, 3 RX <- U0TXD, 4 EN, 5 IO0, 6 VTref
- **J4** — AVR ISP 2x3 (стандарт Atmel), **J5** — UPDI, **J6** — MSP430 SBW, **J7** — AUX
- **JP1** — перемичка: замкнена = Pico живить ціль 3.3 В (до ~200 мА)
- **SW1** — скидання Pico (RUN), **SW2** — ручний RESET цілі

## ESP32
- Прошивка (усі ESP32): UART через J3, esptool / ESP-IDF. Вхід у bootloader: IO0=0 під час імпульсу EN.
- Відладка класичного ESP32 — JTAG через J2: IO13=TCK, IO14=TMS, IO12=TDI, IO15=TDO, EN=nRESET.
- ESP32-C3/C6/S3/H2 мають вбудований USB-JTAG — їм програматор не потрібен.

## Відомі обмеження v1
- Лише 3.3 В цілі; у v2 додати SN74LVC1T45 на кожну лінію, живлені від VTref.
- Схему зібрано генератором без перевірки в KiCad: відкрийте, запустіть ERC і призначте футпринт U1
  (Pico як модуль, напр. бібліотека "RaspberryPi_Pico" або два ряди PinSocket_1x20).

## Механіка та 3D (оновлено)
- Футпринт Pico: `DUNI.pretty/RPi_Pico_THT` (2x20, крок 2.54, ряди 17.78 мм, отвори d2.1 на 11.4x47 мм), 3D: `3dmodels/RPi_Pico.wrl`.
- `DUNI_Probe_v1.kicad_pcb` — плата 53.34x54.71 мм з розставленими Pico та роз'ємами. 3D-перегляд: PCB Editor -> Alt+3.
- Координати роз'ємів (від піна 1 Pico): J2 X=-7.62; J1 X=-10.16,Y=30.48; J3/J4/J5/J6 X=25.40 (Y=0/17.78/30.48/40.64); J7/JP1/J8 X=33.02 (Y=0/27.94/40.64).
- Після "Update PCB from Schematic" (F8) увімкніть "Re-link footprints to schematic symbols based on their reference designators".
