from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(repr=False)
    jwt_secret: str = Field(repr=False)
    environment: Literal["development", "test", "staging", "production"] = "development"
    cors_origins: list[str] = []
    langflow_url: str = ""
    langflow_api_key: str = ""
    langflow_flow_id: str = ""

    # Auth/session
    session_max_age: int = Field(default=86400, gt=0)
    session_cookie_name: str = "session"
    session_cookie_secure: bool = False  # Set True in production over HTTPS
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # CSRF
    csrf_cookie_name: str = "csrf_token"
    csrf_token_expire: int = Field(default=3600, gt=0)
    seed_manager_email: str = "manager.synthetic@example.test"
    seed_manager_password: SecretStr | None = Field(default=None, repr=False, exclude=True)
    # Spatial boundary (synthetic bounding box, Surabaya area approx)
    boundary_lon_min: float = Field(default=112.60, ge=-180, le=180)
    boundary_lon_max: float = Field(default=112.85, ge=-180, le=180)
    boundary_lat_min: float = Field(default=-7.40, ge=-90, le=90)
    boundary_lat_max: float = Field(default=-7.15, ge=-90, le=90)
    boundary_srid: Literal[4326] = 4326
    boundary_source: str = "synthetic-placeholder"
    boundary_is_synthetic: bool = True
    boundary_approved: bool = False
    boundary_revision: str = "synthetic-v1"

    @model_validator(mode="after")
    def validate_security_and_boundary(self) -> "Settings":
        if self.boundary_lon_min >= self.boundary_lon_max:
            raise ValueError("BOUNDARY_LON_MIN must be less than BOUNDARY_LON_MAX")
        if self.boundary_lat_min >= self.boundary_lat_max:
            raise ValueError("BOUNDARY_LAT_MIN must be less than BOUNDARY_LAT_MAX")
        if not self.boundary_source.strip() or not self.boundary_revision.strip():
            raise ValueError("Boundary source and revision are required")
        if self.boundary_is_synthetic and self.boundary_approved:
            raise ValueError("A synthetic boundary cannot be approved for real inventory")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")
        if self.environment in {"staging", "production"}:
            if not self.session_cookie_secure:
                raise ValueError("Staging and production require SESSION_COOKIE_SECURE=true")
            if len(self.jwt_secret.encode()) < 32 or self.jwt_secret.startswith("change-me"):
                raise ValueError("Staging and production require a strong JWT_SECRET")
        return self


settings = Settings()  # type: ignore[call-arg]
