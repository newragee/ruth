#include "audio_io.h"
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2s_std.h"
#include "esp_log.h"

static const char *TAG = "audio_io";

static i2s_chan_handle_t s_rx = NULL;
static i2s_chan_handle_t s_tx = NULL;
static uint32_t s_tx_rate = 22050;

static esp_err_t init_rx(void)
{
    i2s_chan_config_t cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    ESP_ERROR_CHECK(i2s_new_channel(&cfg, NULL, &s_rx));

    i2s_std_config_t std = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(MIC_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = MIC_BCLK_GPIO,
            .ws   = MIC_WS_GPIO,
            .dout = I2S_GPIO_UNUSED,
            .din  = MIC_SD_GPIO,
            .invert_flags = {0},
        },
    };
    // INMP441 L/R=GND -> данные в левом слоте.
    std.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;

    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_rx, &std));
    ESP_ERROR_CHECK(i2s_channel_enable(s_rx));
    return ESP_OK;
}

static esp_err_t init_tx(uint32_t rate)
{
    i2s_chan_config_t cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_MASTER);
    ESP_ERROR_CHECK(i2s_new_channel(&cfg, &s_tx, NULL));

    i2s_std_config_t std = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(rate),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = SPK_BCLK_GPIO,
            .ws   = SPK_LRC_GPIO,
            .dout = SPK_DIN_GPIO,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = {0},
        },
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_tx, &std));
    ESP_ERROR_CHECK(i2s_channel_enable(s_tx));
    s_tx_rate = rate;
    return ESP_OK;
}

esp_err_t audio_io_init(void)
{
    ESP_ERROR_CHECK(init_rx());
    ESP_ERROR_CHECK(init_tx(s_tx_rate));
    ESP_LOGI(TAG, "I2S init OK: mic=16k(in32→16), spk=%lu", (unsigned long)s_tx_rate);
    return ESP_OK;
}

size_t audio_mic_read(int16_t *buf, size_t n_samples)
{
    static int32_t scratch[1024];
    size_t got = 0;
    while (got < n_samples) {
        size_t chunk = n_samples - got;
        if (chunk > sizeof(scratch) / sizeof(scratch[0])) chunk = sizeof(scratch) / sizeof(scratch[0]);
        size_t bytes_read = 0;
        if (i2s_channel_read(s_rx, scratch, chunk * sizeof(int32_t), &bytes_read, pdMS_TO_TICKS(200)) != ESP_OK) {
            break;
        }
        size_t n = bytes_read / sizeof(int32_t);
        // INMP441: данные в верхних 24 битах 32-битного слова.
        // Сдвиг на 14 даёт 16-битное PCM с приличным усилением для речи на 30 см.
        for (size_t i = 0; i < n; i++) {
            int32_t s = scratch[i] >> 14;
            if (s > 32767) s = 32767;
            else if (s < -32768) s = -32768;
            buf[got + i] = (int16_t)s;
        }
        got += n;
    }
    return got;
}

esp_err_t audio_spk_set_sample_rate(uint32_t hz)
{
    if (hz == s_tx_rate) return ESP_OK;
    ESP_LOGI(TAG, "Spk re-init: %lu -> %lu", (unsigned long)s_tx_rate, (unsigned long)hz);
    i2s_channel_disable(s_tx);
    i2s_del_channel(s_tx);
    s_tx = NULL;
    return init_tx(hz);
}

esp_err_t audio_spk_write(const int16_t *buf, size_t n_samples)
{
    size_t written = 0;
    return i2s_channel_write(s_tx, buf, n_samples * sizeof(int16_t), &written, pdMS_TO_TICKS(2000));
}

void audio_spk_emergency_tone(void)
{
    // меандр 600 Гц на 600 мс — без выделения памяти, генерим прямо в стек
    const uint32_t rate = s_tx_rate;
    const uint32_t freq = 600;
    const uint32_t period_samples = rate / freq;
    const uint32_t total_samples  = rate * 6 / 10;
    int16_t chunk[256];
    uint32_t i = 0;
    while (i < total_samples) {
        for (size_t j = 0; j < sizeof(chunk) / sizeof(chunk[0]) && i < total_samples; j++, i++) {
            chunk[j] = ((i / (period_samples / 2)) & 1) ? 12000 : -12000;
        }
        audio_spk_write(chunk, sizeof(chunk) / sizeof(chunk[0]));
    }
}
