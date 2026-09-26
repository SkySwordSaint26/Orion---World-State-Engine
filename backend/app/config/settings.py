import json
import os
from typing import List, Union
from pydantic import field_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    HAS_PYDANTIC_SETTINGS = True
except ImportError:
    from pydantic import BaseModel as BaseSettings
    SettingsConfigDict = None
    HAS_PYDANTIC_SETTINGS = False


class Settings(BaseSettings):
    if HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )

    # Core App
    PROJECT_NAME: str = "Orion World State Engine"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "orion-wse-super-secret-key-change-in-production-random-bytes"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database & Cache
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/orion"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # LLM Settings
    LLM_PROVIDER: str = "ollama"  # ollama | openai | mock
    OLLAMA_URL: str = "http://localhost:11434/api/chat"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    # Extraction calls: Ollama's default context is 4096 tokens (prompts beyond it are truncated silently) and
    # generation is unbounded (a looping answer runs into the request timeout).
    OLLAMA_NUM_CTX: int = 8192
    OLLAMA_NUM_PREDICT: int = 4096
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Extraction execution: "celery" enqueues one ordered job task on the Celery worker (requires Redis);
    # "background" runs the same ordered job in-process via FastAPI BackgroundTasks (local dev, no Redis).
    EXTRACTION_EXECUTOR: str = "background"  # celery | background
    EXTRACTION_PIPELINE: str = "monolithic"  # monolithic (one LLM call per chunk) | split (4 focused stages, Phase 7)
    # Split pipeline only. False (default): any invalid item fails its stage. True: invalid items are dropped (each is
    # logged with its reasons) and the stage fails only if it produced items and none of them is valid.
    ALLOW_PARTIAL_STAGE: bool = False

    # File Storage
    STORAGE_DIR: str = "./storage"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "*"
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return [v]
        return v


settings = Settings()
