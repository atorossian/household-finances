from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aws_region: str = Field(default="eu-west-1", alias="AWS_REGION")
    app_env: str = Field(default="dev", alias="APP_ENV")
    secret_key: str = Field(alias="SECRET_KEY")
    db_url: Optional[str] = Field(default=None, alias="DB_URL")
    s3_bucket: Optional[str] = Field(default=None, alias="S3_BUCKET")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    encoding_algorithm: str = Field(default="HS256", alias="ENCODING_ALGORITHM")

    # Guarantees / nice errors early
    @field_validator("jwt_secret", "s3_bucket")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("required setting is empty")
        return v


# Global settings instance
settings = Settings()
