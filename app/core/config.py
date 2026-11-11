from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    cors_origins: list[str] = []
    langflow_url: str = ""
    langflow_api_key: str = ""
    langflow_flow_id: str = ""


settings = Settings()  # type: ignore[call-arg]
