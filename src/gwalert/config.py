"""Environment-backed settings for gridworks-alerts."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = ".env"


class Settings(BaseSettings):
    # Defaults are a working dev pair: the gridworks-data dev container as
    # the read-only role, and an alert-manager on loopback with its own
    # dev-default token. Production values come from .env.
    db_url: SecretStr = SecretStr(
        "postgresql+psycopg2://gw_alerts:gw_alerts@localhost:5433/tsdb"
    )
    alert_manager_url: str = "http://127.0.0.1:8000"
    alert_manager_token: SecretStr = SecretStr("dev-alert-token")
    # Send one synthetic alert at start-up to prove the delivery path
    # (gwalert -> alert-manager -> Telegram) without touching the database.
    synthetic_alert: bool = False
    opsgenie_api_key: SecretStr = SecretStr("")
    opsgenie_team_id: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_prefix="GWALERT_",
        env_nested_delimiter="__",
        extra="ignore",
    )
