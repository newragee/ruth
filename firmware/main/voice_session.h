#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

// Записывает PCM16-моно из микрофона в PSRAM-буфер с простым энергетическим VAD,
// затем загружает на сервер и проигрывает потоковый ответ.
// Возвращает ESP_OK даже при пустом ответе; ESP_FAIL — при сетевой ошибке.
esp_err_t voice_session_run(void);
