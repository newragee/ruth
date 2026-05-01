-- Migration 002: voice pipeline tables (voice_logs + user_settings)
-- Family/family_members уже описаны в schema1.sql.
-- Применять идемпотентно: CREATE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS public.voice_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    audio_path      VARCHAR,
    duration_sec    DOUBLE PRECISION,
    transcript      TEXT,
    stt_language    VARCHAR,
    stt_confidence  DOUBLE PRECISION,
    nlu_intent      VARCHAR,
    nlu_slots       JSON,
    sentiment_label VARCHAR,
    sentiment_score DOUBLE PRECISION,
    entailment_label VARCHAR,
    entailment_score DOUBLE PRECISION,
    response_text   TEXT,
    is_emergency    BOOLEAN NOT NULL DEFAULT false,
    source          VARCHAR,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_voice_logs_user_id ON public.voice_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_voice_logs_intent  ON public.voice_logs (nlu_intent);
CREATE INDEX IF NOT EXISTS ix_voice_logs_emerg   ON public.voice_logs (is_emergency) WHERE is_emergency = true;

CREATE TABLE IF NOT EXISTS public.user_settings (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    address_name  VARCHAR,
    voice         VARCHAR NOT NULL DEFAULT 'ru_RU-irina-medium',
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT now()
);
