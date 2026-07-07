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
    alert_manager_url: str = "http://localhost:8000"
    alert_manager_token: SecretStr = SecretStr("")
    opsgenie_api_key: SecretStr = SecretStr("")
    opsgenie_team_id: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_prefix="GWALERT_",
        env_nested_delimiter="__",
        extra="ignore",
    )
