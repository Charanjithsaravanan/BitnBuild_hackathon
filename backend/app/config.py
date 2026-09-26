from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LabForge Experiment Platform"
    environment: str = "development"
    database_url: str = "sqlite:///./labforge.db"
    redis_url: str | None = None
    jwt_secret: str = "change-me-in-development-only"
    jwt_expire_minutes: int = 60
    participant_session_hours: int = 24
    access_token_cookie_name: str = "access_token"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    max_body_bytes: int = 4_000_000
    auth_rate_limit_per_minute: int = 10
    public_rate_limit_per_minute: int = 120
    require_https_in_production: bool = True
    trusted_hosts: str = "localhost,127.0.0.1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]

    def validate_production(self) -> None:
        if self.environment.lower() == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret == "change-me-in-development-only":
                raise RuntimeError("Production requires JWT_SECRET with at least 32 characters")
            if self.require_https_in_production and not self.cors_origin_list:
                raise RuntimeError("Production CORS configuration is required")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
