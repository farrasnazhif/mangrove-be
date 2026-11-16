from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    cors_origins: list[str] = []
    langflow_url: str = ""
    langflow_api_key: str = ""
    langflow_flow_id: str = ""

    # Auth/session
    session_secret: str = "change-me-session"
    session_max_age: int = 86400  # 1 day in seconds
    session_cookie_name: str = "session"
    session_cookie_secure: bool = False  # Set True in production over HTTPS
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # CSRF
    csrf_cookie_name: str = "csrf_token"
    csrf_token_expire: int = 3600  # seconds
    # Spatial boundary (synthetic bounding box, Surabaya area approx)
    boundary_lon_min: float = 112.60
    boundary_lon_max: float = 112.85
    boundary_lat_min: float = -7.40
    boundary_lat_max: float = -7.15
    boundary_srid: int = 4326
    boundary_source: str = "synthetic-placeholder"


settings = Settings()  # type: ignore[call-arg]
