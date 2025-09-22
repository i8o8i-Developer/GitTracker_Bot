"""
Configuration Management For GitTracker Bot.
Uses Environment Variables With Sensible Defaults For Production Deployment.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database Configuration Settings."""
    host: str = "127.0.0.1"
    user: str = "root"
    password: str = ""
    name: str = "Tracer_Bot"
    port: int = 3306

    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """Create Database Config From Environment Variables."""
        return cls(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            name=os.getenv('DB_NAME', 'Tracer_Bot'),
            port=int(os.getenv('DB_PORT', '3306'))
        )


@dataclass
class TelegramConfig:
    """Telegram Bot Configuration Settings."""
    token: str
    webhook_secret: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'TelegramConfig':
        """Create Telegram Config From Environment Variables."""
        token = os.getenv('TELEGRAM_TOKEN')
        if not token:
            raise ValueError("TELEGRAM_TOKEN Environment Variable Is Required")

        return cls(
            token=token,
            webhook_secret=os.getenv('TELEGRAM_WEBHOOK_SECRET')
        )


@dataclass
class GitHubConfig:
    """GitHub API Configuration Settings."""
    client_id: str
    client_secret: str
    webhook_secret: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'GitHubConfig':
        """Create GitHub Config From Environment Variables."""
        client_id = os.getenv('GITHUB_CLIENT_ID')
        client_secret = os.getenv('GITHUB_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError("GITHUB_CLIENT_ID And GITHUB_CLIENT_SECRET environment Variables Are Required")

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            webhook_secret=os.getenv('GITHUB_WEBHOOK_SECRET')
        )


@dataclass
class ServerConfig:
    """Server Configuration Settings."""
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    webhook_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'ServerConfig':
        """Create Server Config From Environment Variables."""
        return cls(
            host=os.getenv('SERVER_HOST', '0.0.0.0'),
            port=int(os.getenv('SERVER_PORT', '5000')),
            debug=os.getenv('DEBUG', 'False').lower() == 'true',
            webhook_url=os.getenv('WEBHOOK_URL')
        )


@dataclass
class Config:
    """Main Configuration Class."""
    database: DatabaseConfig
    telegram: TelegramConfig
    github: GitHubConfig
    server: ServerConfig

    @classmethod
    def from_env(cls) -> 'Config':
        """Create Complete Config From Environment Variables."""
        return cls(
            database=DatabaseConfig.from_env(),
            telegram=TelegramConfig.from_env(),
            github=GitHubConfig.from_env(),
            server=ServerConfig.from_env()
        )


# Global Config Instance
config = Config.from_env()