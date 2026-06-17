#pragma once
#include "esp_err.h"

// Блокирующая инициализация WiFi STA, ждёт IP. SSID/PASS из Kconfig.
esp_err_t wifi_sta_start_blocking(void);
