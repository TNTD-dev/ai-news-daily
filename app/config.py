"""
Configuration module for the AI News Aggregator application.

This module uses Pydantic Settings to load and validate environment variables
from a .env file. It provides type-safe, validated configuration with clear
error messages if required values are missing or invalid.

Architecture:
    - Each domain (database, openai, email, scraping) has its own config class
    - All config classes inherit from BaseSettings for automatic env var loading
    - Nested configs are initialized in AppConfig.__init__ to ensure .env is loaded first
    - A global `settings` instance provides singleton access throughout the app

Usage:
    ```python
    from app.config import settings
    
    # Access configuration with full type hints and validation
    db_url = settings.database.url
    openai_key = settings.openai.api_key
    email_host = settings.email.host
    channels = settings.scraping.youtube_channels
    ```

Environment Variables:
    See example.env file for all required and optional environment variables.
    Copy example.env to .env and fill in your actual values.
"""

from pathlib import Path
from typing import Any, List

from dotenv import load_dotenv
from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Load .env file from project root
# This ensures environment variables are available before Pydantic tries to read them
project_root: Path = Path(__file__).parent.parent
env_path: Path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)


class DatabaseConfig(BaseSettings):
    """
    PostgreSQL database configuration.
    
    Attributes:
        url: PostgreSQL connection string in format:
            postgresql://[user]:[password]@[host]:[port]/[database]
        echo: Enable SQLAlchemy query logging (useful for debugging)
    """

    model_config: SettingsConfigDict = SettingsConfigDict(
        env_prefix="", case_sensitive=True
    )

    url: str = Field(..., alias="DATABASE_URL", description="PostgreSQL connection string")
    echo: bool = Field(default=False, description="SQLAlchemy echo mode")


class OpenAIConfig(BaseSettings):
    """
    OpenAI API configuration.
    
    Environment variables are prefixed with "OPENAI_", so:
    - OPENAI_API_KEY maps to api_key
    - OPENAI_MODEL maps to model
    
    Attributes:
        api_key: Your OpenAI API key (required)
        model: Model name to use (default: "gpt-4")
    """

    model_config: SettingsConfigDict = SettingsConfigDict(
        env_prefix="OPENAI_", case_sensitive=True
    )

    api_key: str = Field(..., description="OpenAI API key")
    model: str = Field(default="gpt-4", description="OpenAI model name")


class EmailConfig(BaseSettings):
    """
    SMTP email configuration.
    
    All email-related environment variables use explicit aliases to match
    common naming conventions (SMTP_HOST, FROM_EMAIL, etc.).
    
    Attributes:
        host: SMTP server hostname (e.g., smtp.gmail.com)
        port: SMTP server port (587 for TLS, 465 for SSL, default: 587)
        user: SMTP username (usually your email address)
        password: SMTP password (use app password for Gmail)
        from_email: Sender email address (validated as EmailStr)
        to_email: Recipient email address (validated as EmailStr)
    """

    model_config: SettingsConfigDict = SettingsConfigDict(
        env_prefix="", case_sensitive=True
    )

    host: str = Field(..., alias="SMTP_HOST", description="SMTP server host")
    port: int = Field(default=587, alias="SMTP_PORT", description="SMTP server port")
    user: str = Field(..., alias="SMTP_USER", description="SMTP username")
    password: str = Field(..., alias="SMTP_PASSWORD", description="SMTP password")
    from_email: EmailStr = Field(..., alias="FROM_EMAIL", description="Sender email address")
    to_email: EmailStr = Field(..., alias="TO_EMAIL", description="Recipient email address")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """
        Validate SMTP port is in valid range (1-65535).
        
        Args:
            v: Port number to validate
            
        Returns:
            Validated port number
            
        Raises:
            ValueError: If port is outside valid range
        """
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class ScrapingConfig(BaseSettings):
    """
    Scraping parameters configuration.
    
    Attributes:
        hours_lookback: Number of hours to look back when scraping content (default: 24)
        max_articles: Maximum number of articles to process (default: 10)
        youtube_channels: List of YouTube channel IDs or URLs (parsed from comma-separated string)
    """

    model_config: SettingsConfigDict = SettingsConfigDict(
        env_prefix="", case_sensitive=True
    )

    hours_lookback: int = Field(
        default=24,
        alias="SCRAPING_HOURS_LOOKBACK",
        description="Hours to look back for content",
    )
    max_articles: int = Field(
        default=10,
        alias="SCRAPING_MAX_ARTICLES",
        description="Maximum number of articles to process",
    )
    youtube_channels: List[str] = Field(
        default_factory=list,
        alias="YOUTUBE_CHANNELS",
        description="List of YouTube channel IDs/URLs",
    )

    @field_validator("hours_lookback", "max_articles")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """
        Validate that hours and max_articles are positive integers.
        
        Args:
            v: Integer value to validate
            
        Returns:
            Validated positive integer
            
        Raises:
            ValueError: If value is not positive
        """
        if v <= 0:
            raise ValueError("Value must be a positive integer")
        return v

    @field_validator("youtube_channels", mode="before")
    @classmethod
    def parse_youtube_channels(cls, v: str | List[str]) -> List[str]:
        """
        Parse comma-separated YouTube channels string into list.
        
        This validator runs before type checking, allowing us to convert
        the environment variable string (e.g., "channel1,channel2,channel3")
        into a proper list of strings.
        
        Args:
            v: Either a comma-separated string or already a list
            
        Returns:
            List of channel IDs/URLs with whitespace stripped
        """
        if isinstance(v, str):
            # Split by comma and strip whitespace
            channels = [channel.strip() for channel in v.split(",") if channel.strip()]
            return channels
        return v


class AppConfig(BaseSettings):
    """
    Main application configuration.
    
    This class aggregates all domain-specific configurations into a single
    settings object. It uses nested BaseSettings classes, each of which
    automatically reads from environment variables.
    
    Nested Config Initialization:
        Each nested config (DatabaseConfig, OpenAIConfig, etc.) is a separate
        BaseSettings instance. This allows each to have its own env_prefix and
        read environment variables independently. The __init__ method ensures:
        
        1. .env file is loaded before any config reads env vars
        2. Each nested config is initialized if not provided in kwargs
        3. This pattern allows for easy testing by passing mock configs
        
    Attributes:
        database: PostgreSQL database configuration
        openai: OpenAI API configuration
        email: SMTP email configuration
        scraping: Content scraping parameters
    """

    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file=str(env_path) if env_path.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    database: DatabaseConfig
    openai: OpenAIConfig
    email: EmailConfig
    scraping: ScrapingConfig

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize configuration with proper environment variable loading.
        
        This method ensures the .env file is loaded before nested configs
        try to read environment variables. It also provides default initialization
        for nested configs, making the configuration system work out-of-the-box
        while still allowing override for testing.
        
        Args:
            **kwargs: Optional keyword arguments to override nested configs.
                     Useful for testing with mock configurations.
        
        Note:
            The nested config initialization pattern works as follows:
            - Each nested config class (DatabaseConfig, etc.) inherits from BaseSettings
            - BaseSettings automatically reads from environment variables
            - We initialize them here to ensure .env is loaded first
            - If kwargs contains a config, we use it (useful for testing)
            - Otherwise, we create a new instance that reads from env vars
        """
        # Ensure .env is loaded before nested configs read environment variables
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try to load from current directory as fallback
            load_dotenv()

        # Initialize nested configs if not provided in kwargs
        # This allows each nested config to read its own environment variables
        # independently, while still allowing override for testing
        if "database" not in kwargs:
            kwargs["database"] = DatabaseConfig()
        if "openai" not in kwargs:
            kwargs["openai"] = OpenAIConfig()
        if "email" not in kwargs:
            kwargs["email"] = EmailConfig()
        if "scraping" not in kwargs:
            kwargs["scraping"] = ScrapingConfig()

        super().__init__(**kwargs)


# Global settings instance (singleton pattern)
# This provides a single source of truth for configuration throughout the app
# Import this in other modules: `from app.config import settings`
settings: AppConfig = AppConfig()
