from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://taazi:taazi@localhost:5432/taazi",
        description="PostgreSQL connection string (asyncpg driver)",
    )

    # --- Cache ---
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string",
    )

    # --- AI / LLM ---
    nvidia_api_key: SecretStr = Field(
        default="",
        description="NVIDIA NIM API key for LLM inference (global default)",
    )
    nvidia_nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="NVIDIA NIM API base URL (global default)",
    )
    nvidia_api_key_summarizer: SecretStr = Field(
        default="",
        description="Per-persona API key for summarizer (falls back to NVIDIA_API_KEY)",
    )
    nvidia_nim_base_url_summarizer: str = Field(
        default="",
        description="Per-persona base URL for summarizer (falls back to NVIDIA_NIM_BASE_URL)",
    )
    nvidia_api_key_question_setter: SecretStr = Field(
        default="",
        description="Per-persona API key for question setter (falls back to NVIDIA_API_KEY)",
    )
    nvidia_nim_base_url_question_setter: str = Field(
        default="",
        description="Per-persona base URL for question setter (falls back to NVIDIA_NIM_BASE_URL)",
    )
    models_config_path: str = Field(
        default=str(Path(__file__).resolve().parent / "ai" / "config" / "models.yaml"),
        description="Path to the model registry YAML file",
    )

    # --- Auth ---
    nextauth_secret: SecretStr = Field(
        default="dev-secret",
        description="Secret used for JWT signing (shared with NextAuth)",
    )
    access_token_expire_minutes: int = Field(
        default=60 * 24 * 7,
        ge=1,
        le=60 * 24 * 30,
        description="JWT access token expiry in minutes (default: 7 days)",
    )

    # --- App ---
    environment: str = Field(
        default="development",
        description="Runtime environment: development | staging | production",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG | INFO | WARNING | ERROR",
    )
    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    # --- Admin ---
    admin_email: str = Field(
        default="admin@taazi.app",
        description="Default admin email (created on first seed)",
    )
    admin_password: SecretStr = Field(
        default="change-me",
        description="Default admin password",
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        origins = [o.strip() for o in v.split(",") if o.strip()]
        if not origins:
            raise ValueError("cors_origins must contain at least one origin")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("database_url must be a PostgreSQL connection string")
        if "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "prepared_statement_cache_size=0" not in v:
            sep = "&" if "?" in v else "?"
            v = f"{v}{sep}prepared_statement_cache_size=0"
        return v

    def get_persona_credentials(self, persona: str) -> tuple[str, str]:
        key_field = f"nvidia_api_key_{persona}"
        url_field = f"nvidia_nim_base_url_{persona}"
        api_key = getattr(self, key_field, SecretStr(""))
        base_url = getattr(self, url_field, "")
        return (
            api_key.get_secret_value() or self.nvidia_api_key.get_secret_value(),
            base_url or self.nvidia_nim_base_url,
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
