from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    LLM_API_URL: str
    LLM_API_KEY: str

    # --- Speech / NLP pipeline ---
    WHISPER_MODEL: str = "small"
    WHISPER_DEVICE: str = "cpu"          # "cuda" если есть GPU
    WHISPER_COMPUTE_TYPE: str = "int8"   # "float16" для GPU
    WHISPER_LANGUAGE: str = "ru"

    PIPER_VOICE: str = "ru_RU-irina-medium"
    PIPER_MODELS_DIR: str = "models/piper"

    NLI_SENTIMENT_MODEL: str = "seara/rubert-tiny2-russian-sentiment"
    NLI_ENTAILMENT_MODEL: str = "cointegrated/rubert-base-cased-nli-threeway"

    VOICE_STORAGE_DIR: str = "data/voice"
    VOICE_SAMPLE_RATE: int = 16000

    model_config = ConfigDict(env_file=".env", extra="ignore")

settings = Settings()
