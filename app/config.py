from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./calendar.db"
    secret_key: str = "dev-secret-change-me"
    session_days: int = 30
    cookie_secure: bool = False  # True em produção (HTTPS)
    timezone: str = "America/Sao_Paulo"  # fuso em que as datas são digitadas e exibidas
    rate_limit_enabled: bool = True

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()
