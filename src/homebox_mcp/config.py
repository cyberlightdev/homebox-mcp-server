"""Configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    homebox_url: str = "http://homebox:7745"
    homebox_email: str
    homebox_password: str
    mcp_port: int = 8100
    session_file: str = "/data/sessions.json"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
