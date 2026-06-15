# Ruth Speaker — прошивка ESP32-S3

Прошивка для ESP32-S3-DevKitC-1 (N16R8) + INMP441 + MAX98357A,
которая ведёт диалог через сервер из этого репозитория.

## Распиновка

```
INMP441 (I2S0)              MAX98357A (I2S1)
SD   → GPIO 4               DIN  → GPIO 7
WS   → GPIO 5               BCLK → GPIO 15
SCK  → GPIO 6               LRC  → GPIO 16
L/R  → GND                  GAIN → 3.3V (9 dB)
VDD  → 3.3V                 SD   → 3.3V (enable)
GND  → GND                  VIN  → 5V (USB)
                            GND  → GND
```

Активация по умолчанию — кнопка **BOOT (GPIO0)**. После сборки
Phase 2 (см. ниже) переключается на голосовое «Hi ESP».

## Phase 1 — собрать и прошить (button mode)

### 1. Подготовка ESP-IDF v5.3+

```bash
# единоразово
git clone -b v5.3.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32s3 && . ./export.sh
```

### 2. Конфиг

```bash
cd C:\Codeeee\Ruth-main-gemma3\firmware
idf.py set-target esp32s3
idf.py menuconfig
```

В `Ruth Speaker Configuration`:
- **WiFi → SSID/PASSWORD** — твоя сеть.
- **Backend → Voice converse_raw endpoint** — `http://<IP сервера>:8000/api/v1/voice/converse_raw`.
- **Backend → JWT bearer token** — получи через `POST /api/v1/auth/login` и вставь.
- **Activation → Push-to-talk (BOOT button)** (на Phase 1).

### 3. Получить JWT

```powershell
curl -s -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"voicetester\",\"password\":\"voicetester123\"}'
# → копируешь access_token в menuconfig
```

### 4. Сборка и прошивка

```bash
idf.py build
idf.py -p COM5 flash monitor    # подставь свой порт
```

В мониторе увидишь:
```
I (xxx) wifi: IP 192.168.1.42
I (xxx) audio_io: I2S init OK
I (xxx) app: Нажми BOOT для разговора...
```

Жми BOOT → говори → отпускаешь не нужно (запись стопится по VAD после ~800 мс тишины) → играет ответ через MAX98357A.

## Phase 2 — wake word «Hi ESP» через esp-sr

В `idf_component.yml` уже подключён `espressif/esp-sr`. Чтобы заменить
BOOT-кнопку на wake-word, добавь файл `main/wake_word.c`:

```c
#include "wake_word.h"
#include "audio_io.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_afe_sr_models.h"
#include "model_path.h"

static esp_afe_sr_iface_t *s_afe = NULL;
static esp_afe_sr_data_t  *s_data = NULL;
static srmodel_list_t     *s_models = NULL;
static const char *TAG = "wake";

void wake_word_init(void) {
    s_models = esp_srmodel_init("model");
    afe_config_t cfg = AFE_CONFIG_DEFAULT();
    cfg.wakenet_model_name = esp_srmodel_filter(s_models, ESP_WN_PREFIX, NULL);
    cfg.aec_init = false;
    cfg.pcm_config.total_ch_num = 1;
    cfg.pcm_config.mic_num = 1;
    cfg.pcm_config.ref_num = 0;
    cfg.pcm_config.sample_rate = 16000;
    s_afe = (esp_afe_sr_iface_t *)&ESP_AFE_SR_HANDLE;
    s_data = s_afe->create_from_config(&cfg);
    ESP_LOGI(TAG, "WakeNet ready");
}

void wake_word_wait(void) {
    int chunk = s_afe->get_feed_chunksize(s_data);
    int16_t *buf = malloc(chunk * sizeof(int16_t));
    for (;;) {
        audio_mic_read(buf, chunk);
        s_afe->feed(s_data, buf);
        afe_fetch_result_t *r = s_afe->fetch(s_data);
        if (r && r->wakeup_state == WAKENET_DETECTED) {
            free(buf);
            return;
        }
    }
}
```

И раскомментируй `extern` в `app_main.c`, выбери в menuconfig
**Activation → Wake word**. Пересобери.

Готовая модель `wn9_hiesp` («Hi ESP») зашьётся в раздел `model` автоматически
при `idf.py build` через esp-sr. Для русского ключевого слова обучается
через [Espressif Wake Word Training](https://github.com/espressif/esp-sr/blob/master/docs/wake_word_engine/ESP_Wake_Words_Customization.md).

## Поток данных (что именно происходит)

1. Активация (BOOT или wake-word).
2. INMP441 → I2S0 → 32-bit → конверт >>14 → PCM16 16 kHz mono.
3. Энергетический VAD: 20-мс кадры; стоп после ~800 мс тишины (или 8 с max).
4. Собираем WAV (44 байта header + PCM) в PSRAM.
5. `POST /api/v1/voice/converse_raw`, `Content-Type: audio/wav`, `Authorization: Bearer <JWT>`.
6. Ответ — стрим WAV. Парсим header в первом чанке (`X-TTS-Sample-Rate` подтверждает rate), переинициализируем I2S1, льём PCM в MAX98357A по мере прихода.
7. Если в заголовке `X-Is-Emergency: 1` — после ответа играем сигнал тревоги (меандр 600 Гц 600 мс).

## Тонкости

- **JWT срок жизни — 30 мин.** На Phase 1 ОК для теста. На production надо хранить refresh-логику в NVS и логиниться по device-token.
- **HTTPS.** В Phase 1 сервер локальный, ходим по HTTP. Для HTTPS включи
  `esp_crt_bundle_attach = esp_crt_bundle_attach` в `voice_session.c` (header
  `esp_crt_bundle.h`), убери `skip_cert_common_name_check`.
- **Sample rate Piper.** Голос `ru_RU-irina-medium` отдаёт 22050 Hz. I2S1
  переинициализируется на лету при первом ответе.
- **Энергетический VAD прост и шумочувствителен.** Phase 2 заменит его на
  AFE VAD из esp-sr (поле `r->vad_state`).
- **Bluetooth не используется.** Если хочешь BLE-provisioning — добавим
  отдельным компонентом.
