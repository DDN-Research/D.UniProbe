/*
 * D.UNI Probe v1 - board configuration (Raspberry Pi Pico, RP2040)
 * Based on Raspberry Pi Debugprobe (MIT licence).
 * Pin map matches KiCAD/Ver 1/DUNI_Probe_v1.kicad_sch
 */
#ifndef BOARD_DUNI_CONFIG_H_
#define BOARD_DUNI_CONFIG_H_

#define PROBE_IO_RAW
#define PROBE_CDC_UART

/* ---- SWD (PIO) ---- */
#define PROBE_SM 0
#define PROBE_PIN_OFFSET 2
#define PROBE_PIN_SWCLK (PROBE_PIN_OFFSET + 0) /* GP2 = SWCLK / TCK */
#define PROBE_PIN_SWDIO (PROBE_PIN_OFFSET + 1) /* GP3 = SWDIO / TMS */
#define PROBE_PIN_RESET 1                      /* GP1 = nRESET (open drain) */

/* ---- JTAG (bit-bang, CMSIS-DAP JTAG port) ---- */
#define DUNI_PIN_TDI   6   /* GP6 */
#define DUNI_PIN_TDO   7   /* GP7 (also SWO) */
#define DUNI_PIN_nTRST 8   /* GP8 */

/* ---- UART bridge (USB CDC) ---- */
#define PROBE_UART_TX 4
#define PROBE_UART_RX 5
#define PROBE_UART_INTERFACE uart1
#define PROBE_UART_BAUDRATE 115200

/* ---- ESP32 auto-boot (esptool DTR/RTS emulation, open drain) ---- */
#define DUNI_PIN_ESP_EN  10 /* GP10 -> ESP32 EN  */
#define DUNI_PIN_ESP_IO0 11 /* GP11 -> ESP32 IO0 */

/* ---- LEDs ---- */
#define DUNI_HEARTBEAT_LED      25 /* on-board LED: 1 Hz = working, 5 Hz = no USB host */
#define PROBE_DAP_RUNNING_LED   15 /* D1 on the D.UNI board */

#define PROBE_PRODUCT_STRING "D.UNI Probe v1.1 (CMSIS-DAP)"

#endif
