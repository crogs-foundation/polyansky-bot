from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from environs import Env


@dataclass
class DatabaseConfig:
    """Database configuration."""

    path: Path
    echo: bool = False


@dataclass
class BotConfig:
    """Telegram bot configuration."""

    token: str
    admin_ids: list[int]
    use_webhook: bool = False
    webhook_url: Optional[str] = None
    webhook_path: str = "/webhook"
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8080


@dataclass
class Config:
    """Application configuration."""

    bot: BotConfig
    database: DatabaseConfig


def load_config(path: Optional[str] = None) -> Config:
    """
    Load configuration from environment variables.

    Args:
        path: Path to .env file. If None, uses .env in current directory.

    Returns:
        Loaded configuration object.

    Raises:
        environs.EnvError: If required environment variables are missing.
    """
    env = Env()
    env.read_env(path)

    return Config(
        bot=BotConfig(
            token=env.str("TELEGRAM_TOKEN"),
            admin_ids=env.list("ADMIN_IDS", [], subcast=int),
            use_webhook=env.bool("USE_WEBHOOK", False),
            webhook_url=env.str("WEBHOOK_URL", None),
            webhook_path=env.str("WEBHOOK_PATH", "/webhook"),
            webapp_host=env.str("WEBAPP_HOST", "0.0.0.0"),
            webapp_port=env.int("WEBAPP_PORT", 8080),
        ),
        database=DatabaseConfig(
            path=Path(env.str("DB_PATH", "data/polyansky.db")),
            echo=env.bool("DB_ECHO", False),
        ),
    )
