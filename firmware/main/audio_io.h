#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

// --- I2S pinout (ESP32-S3-DevKitC-1 N16R8) ---
#define MIC_BCLK_GPIO     6
#define MIC_WS_GPIO       5
#define MIC_SD_GPIO       4

#define SPK_BCLK_GPIO    15
#define SPK_LRC_GPIO     16
#define SPK_DIN_GPIO      7

#define MIC_SAMPLE_RATE  16000   // STT/wake-word ждут 16 kHz mono

esp_err_t audio_io_init(void);

// Чтение `n_samples` сэмплов с микрофона (PCM16, mono).
// INMP441 отдаёт 24 бита в 32-битном слоте — конвертится внутри.
size_t audio_mic_read(int16_t *buf, size_t n_samples);

// Переконфигурация выходного I2S под пришедший от сервера sample-rate (Piper ru irina = 22050 Гц).
esp_err_t audio_spk_set_sample_rate(uint32_t hz);

// Запись PCM16-чанка в динамик. Блокирующий до DMA-записи.
esp_err_t audio_spk_write(const int16_t *buf, size_t n_samples);

// Тревожный тон для emergency: меандр ~600 Гц, ~600 мс.
void audio_spk_emergency_tone(void);
