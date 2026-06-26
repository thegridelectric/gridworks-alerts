"""Environment-backed settings for gridworks-alerts."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = ".env"


class Settings(BaseSettings):
    db_url: SecretStr = SecretStr(
        "postgresql+psycopg2://journaldb:journaldb@localhost:5433/journaldb_dev"
    )
    gbo_db_url: SecretStr = SecretStr(
        "postgresql+psycopg2://journaldb:journaldb@localhost:5433/backofficedb_dev"
    )
    telegram_bot_token: SecretStr = SecretStr("")
    google_sheets_credentials_path: str = ""
    google_sheets_spreadsheet_id: str = ""

    model_config = SettingsConfigDict(
        env_prefix="GWALERT_",
        env_nested_delimiter="__",
        extra="ignore",
    )
