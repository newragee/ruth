#include "voice_session.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "sdkconfig.h"
#include "audio_io.h"

static const char *TAG = "session";

#define FRAME_SAMPLES     320            // 20 мс @ 16 kHz
#define FRAME_BYTES       (FRAME_SAMPLES * sizeof(int16_t))
#define MAX_SECONDS       CONFIG_RUTH_RECORD_MAX_SECONDS
#define MAX_SAMPLES       (MIC_SAMPLE_RATE * MAX_SECONDS)
#define MAX_PCM_BYTES     (MAX_SAMPLES * sizeof(int16_t))

#define SILENCE_FRAMES_END  40           // ~800 мс тишины → стоп
#define ENERGY_THRESHOLD    900          // эмпирически для INMP441 @ shift>>14

static uint32_t frame_energy(const int16_t *buf, size_t n)
{
    uint64_t acc = 0;
    for (size_t i = 0; i < n; i++) {
        int32_t s = buf[i];
        acc += (uint32_t)((s < 0 ? -s : s));
    }
    return (uint32_t)(acc / n);
}

// --- WAV-заголовок 16 kHz mono PCM16 для тела запроса ---
static void build_wav_header(uint8_t *hdr, uint32_t pcm_bytes)
{
    uint32_t file_size = 36 + pcm_bytes;
    memcpy(hdr + 0,  "RIFF", 4);
    hdr[4] = file_size & 0xff; hdr[5] = (file_size >> 8) & 0xff;
    hdr[6] = (file_size >> 16) & 0xff; hdr[7] = (file_size >> 24) & 0xff;
    memcpy(hdr + 8,  "WAVE", 4);
    memcpy(hdr + 12, "fmt ", 4);
    hdr[16] = 16; hdr[17] = 0; hdr[18] = 0; hdr[19] = 0;     // fmt chunk size
    hdr[20] = 1;  hdr[21] = 0;                                // PCM
    hdr[22] = 1;  hdr[23] = 0;                                // mono
    hdr[24] = (MIC_SAMPLE_RATE) & 0xff;
    hdr[25] = (MIC_SAMPLE_RATE >> 8) & 0xff;
    hdr[26] = (MIC_SAMPLE_RATE >> 16) & 0xff;
    hdr[27] = (MIC_SAMPLE_RATE >> 24) & 0xff;
    uint32_t bps = MIC_SAMPLE_RATE * 2;                       // byte rate
    hdr[28] = bps & 0xff; hdr[29] = (bps >> 8) & 0xff;
    hdr[30] = (bps >> 16) & 0xff; hdr[31] = (bps >> 24) & 0xff;
    hdr[32] = 2; hdr[33] = 0;                                 // block align
    hdr[34] = 16; hdr[35] = 0;                                // bits per sample
    memcpy(hdr + 36, "data", 4);
    hdr[40] = pcm_bytes & 0xff; hdr[41] = (pcm_bytes >> 8) & 0xff;
    hdr[42] = (pcm_bytes >> 16) & 0xff; hdr[43] = (pcm_bytes >> 24) & 0xff;
}

// ----- запись с VAD -----
static size_t record_with_vad(int16_t *pcm, size_t max_samples)
{
    int16_t frame[FRAME_SAMPLES];
    size_t total = 0;
    int silent = 0;
    int spoke = 0;

    ESP_LOGI(TAG, "Recording (energy VAD)...");
    while (total + FRAME_SAMPLES <= max_samples) {
        size_t got = audio_mic_read(frame, FRAME_SAMPLES);
        if (got == 0) break;
        memcpy(pcm + total, frame, got * sizeof(int16_t));
        total += got;

        uint32_t e = frame_energy(frame, got);
        if (e > ENERGY_THRESHOLD) { spoke = 1; silent = 0; }
        else if (spoke) {
            silent++;
            if (silent >= SILENCE_FRAMES_END) break;
        } else if (total > MIC_SAMPLE_RATE) {
            // 1 с тишины с самого начала → выходим
            break;
        }
    }
    ESP_LOGI(TAG, "Captured %u samples (%.2f s)", (unsigned)total, total / (float)MIC_SAMPLE_RATE);
    return total;
}

// ----- стриминговое воспроизведение ответа -----
typedef struct {
    bool header_seen;
    uint8_t hdr_buf[44];
    size_t  hdr_filled;
    uint32_t sample_rate;
    bool emergency;
} resp_ctx_t;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    resp_ctx_t *ctx = (resp_ctx_t *)evt->user_data;

    switch (evt->event_id) {
    case HTTP_EVENT_ON_HEADER:
        if (evt->header_key && evt->header_value) {
            if (strcasecmp(evt->header_key, "X-Is-Emergency") == 0) {
                ctx->emergency = (evt->header_value[0] == '1');
            }
            if (strcasecmp(evt->header_key, "X-TTS-Sample-Rate") == 0) {
                ctx->sample_rate = strtoul(evt->header_value, NULL, 10);
            }
        }
        break;

    case HTTP_EVENT_ON_DATA: {
        const uint8_t *p = (const uint8_t *)evt->data;
        size_t len = evt->data_len;

        if (!ctx->header_seen) {
            size_t need = 44 - ctx->hdr_filled;
            size_t take = (len < need) ? len : need;
            memcpy(ctx->hdr_buf + ctx->hdr_filled, p, take);
            ctx->hdr_filled += take;
            p   += take;
            len -= take;
            if (ctx->hdr_filled < 44) return ESP_OK;

            uint32_t sr = ctx->hdr_buf[24] | (ctx->hdr_buf[25] << 8) |
                          (ctx->hdr_buf[26] << 16) | (ctx->hdr_buf[27] << 24);
            if (sr > 0 && sr < 96000) ctx->sample_rate = sr;
            audio_spk_set_sample_rate(ctx->sample_rate ? ctx->sample_rate : 22050);
            ctx->header_seen = true;
            ESP_LOGI(TAG, "TTS WAV header: rate=%lu", (unsigned long)ctx->sample_rate);
        }

        if (len > 0) {
            // PCM16, моно → пишем напрямую (data_len чётное в нормальном случае)
            size_t n = len / 2;
            audio_spk_write((const int16_t *)p, n);
        }
        break;
    }
    default: break;
    }
    return ESP_OK;
}

static esp_err_t upload_and_play(const uint8_t *body, size_t body_len, bool *emergency_out)
{
    resp_ctx_t ctx = { .sample_rate = 22050 };

    char auth[768];
    snprintf(auth, sizeof(auth), "Bearer %s", CONFIG_RUTH_JWT);

    esp_http_client_config_t cfg = {
        .url = CONFIG_RUTH_SERVER_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = http_event_handler,
        .user_data = &ctx,
        .timeout_ms = 60000,
        .buffer_size_tx = 1024,
        .buffer_size = 2048,
        .crt_bundle_attach = NULL,                // для https можно подключить esp_crt_bundle_attach
        .skip_cert_common_name_check = true,
    };
    esp_http_client_handle_t cli = esp_http_client_init(&cfg);
    if (!cli) return ESP_FAIL;

    esp_http_client_set_header(cli, "Content-Type", "audio/wav");
    esp_http_client_set_header(cli, "Authorization", auth);
    esp_http_client_set_post_field(cli, (const char *)body, (int)body_len);

    ESP_LOGI(TAG, "POST %s (%u bytes)", CONFIG_RUTH_SERVER_URL, (unsigned)body_len);
    esp_err_t err = esp_http_client_perform(cli);
    int status = esp_http_client_get_status_code(cli);
    ESP_LOGI(TAG, "Response: status=%d, emergency=%d", status, (int)ctx.emergency);
    esp_http_client_cleanup(cli);
    if (emergency_out) *emergency_out = ctx.emergency;
    return (err == ESP_OK && status == 200) ? ESP_OK : ESP_FAIL;
}

esp_err_t voice_session_run(void)
{
    int16_t *pcm = (int16_t *)heap_caps_malloc(MAX_PCM_BYTES, MALLOC_CAP_SPIRAM);
    if (!pcm) {
        ESP_LOGE(TAG, "PSRAM alloc fail");
        return ESP_FAIL;
    }

    size_t n_samples = record_with_vad(pcm, MAX_SAMPLES);
    if (n_samples < (size_t)(MIC_SAMPLE_RATE / 2)) {  // < 500 мс
        ESP_LOGW(TAG, "Too short, abort");
        heap_caps_free(pcm);
        return ESP_OK;
    }

    size_t pcm_bytes = n_samples * sizeof(int16_t);
    size_t body_len  = 44 + pcm_bytes;
    uint8_t *body = (uint8_t *)heap_caps_malloc(body_len, MALLOC_CAP_SPIRAM);
    if (!body) { heap_caps_free(pcm); return ESP_FAIL; }
    build_wav_header(body, pcm_bytes);
    memcpy(body + 44, pcm, pcm_bytes);
    heap_caps_free(pcm);

    bool emergency = false;
    esp_err_t r = upload_and_play(body, body_len, &emergency);
    heap_caps_free(body);

    if (emergency) {
        vTaskDelay(pdMS_TO_TICKS(200));
        audio_spk_emergency_tone();
    }
    return r;
}
