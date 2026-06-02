from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://taazi:taazi@localhost:5432/taazi"
    redis_url: str = "redis://localhost:6379/0"
    nvidia_api_key: str = ""
    nvidia_nim_base_url: str = "https://api.nvcf.nvidia.com/v2/llm/nim"
    nextauth_secret: str = "dev-secret"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    admin_email: str = "admin@taazi.app"
    admin_password: str = "change-me"
    models_config_path: str = str(Path(__file__).resolve().parent / "ai" / "config" / "models.yaml")

    class Config:
        env_file = ".env"


settings = Settings()
