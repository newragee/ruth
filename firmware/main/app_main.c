// Ruth Speaker — entrypoint.
//
// Цикл:
//   wifi_sta_start_blocking()
//   audio_io_init()
//   for (;;):
//     ждём активацию (wake-word или BOOT-кнопка по Kconfig)
//     voice_session_run()  // запись с VAD → POST /converse_raw → стрим в I2S
//
// Wake-word интегрируется отдельным модулем wake_word.c через esp-sr AFE.
// На v1 здесь — упрощённая активация (кнопка). esp-sr WakeNet добавляется
// в wake_word_wait() как замена `wait_button()` (см. README → Phase 2).

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "sdkconfig.h"

#include "wifi_sta.h"
#include "audio_io.h"
#include "voice_session.h"

#define BOOT_BUTTON_GPIO 0
static const char *TAG = "app";

static void wait_for_button_press(void)
{
    gpio_set_direction(BOOT_BUTTON_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(BOOT_BUTTON_GPIO, GPIO_PULLUP_ONLY);
    ESP_LOGI(TAG, "Нажми BOOT для разговора...");
    while (gpio_get_level(BOOT_BUTTON_GPIO) == 1) {
        vTaskDelay(pdMS_TO_TICKS(50));
    }
    // debounce + ждём отпускания
    vTaskDelay(pdMS_TO_TICKS(50));
    while (gpio_get_level(BOOT_BUTTON_GPIO) == 0) {
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

#if CONFIG_RUTH_ACTIVATION_WAKEWORD
// Объявлена в wake_word.c (добавляется по инструкции в README, Phase 2)
extern void wake_word_init(void);
extern void wake_word_wait(void);
#endif

void app_main(void)
{
    ESP_LOGI(TAG, "Boot");

    ESP_ERROR_CHECK(wifi_sta_start_blocking());
    ESP_ERROR_CHECK(audio_io_init());

#if CONFIG_RUTH_ACTIVATION_WAKEWORD
    wake_word_init();
#endif

    for (;;) {
#if CONFIG_RUTH_ACTIVATION_WAKEWORD
        wake_word_wait();
#else
        wait_for_button_press();
#endif
        ESP_LOGI(TAG, "Активация — старт сессии");
        voice_session_run();
    }
}
