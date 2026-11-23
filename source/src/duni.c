/*
 * D.UNI Probe - board extras:
 *  - heartbeat LED on GP25 (on-board Pico LED)
 *  - target nRESET line initialisation (open drain, needed for STM32 "connect under reset")
 */
#include <pico/stdlib.h>
#include "FreeRTOS.h"
#include "task.h"
#include "tusb.h"
#include "board_config.h"
#include "duni.h"

#ifdef DUNI_HEARTBEAT_LED
static TaskHandle_t hb_taskhandle;

/* 1 Hz blink (500 ms on / 500 ms off) while USB is connected to a PC.
 * Fast blink (5 Hz) while USB is not enumerated (e.g. powered from a charger). */
static void heartbeat_thread(void *ptr)
{
    (void) ptr;
    bool on = false;
    for (;;) {
        on = !on;
        gpio_put(DUNI_HEARTBEAT_LED, on);
        vTaskDelay(pdMS_TO_TICKS(tud_ready() ? 500 : 100));
    }
}
#endif

void duni_board_init(void)
{
#ifdef PROBE_PIN_RESET
    /* Open-drain emulation: output latch = 0, direction IN = released (pulled up) */
    gpio_init(PROBE_PIN_RESET);
    gpio_put(PROBE_PIN_RESET, 0);
    gpio_set_dir(PROBE_PIN_RESET, GPIO_IN);
    gpio_pull_up(PROBE_PIN_RESET);
#endif
#ifdef DUNI_HEARTBEAT_LED
    gpio_init(DUNI_HEARTBEAT_LED);
    gpio_set_dir(DUNI_HEARTBEAT_LED, GPIO_OUT);
    gpio_put(DUNI_HEARTBEAT_LED, 0);
#endif
}

void duni_start_tasks(void)
{
#ifdef DUNI_HEARTBEAT_LED
    xTaskCreate(heartbeat_thread, "LED", configMINIMAL_STACK_SIZE, NULL, tskIDLE_PRIORITY + 2, &hb_taskhandle);
#if (configNUMBER_OF_CORES > 1)
    vTaskCoreAffinitySet(hb_taskhandle, (1 << 0));
#endif
#endif
}
