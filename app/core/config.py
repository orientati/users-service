from pydantic_settings import SettingsConfigDict, BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "Users Service"
    SERVICE_VERSION: str = "0.1.0"
    DATABASE_URL: str = "sqlite:///./database.db"
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"
    SERVICE_PORT: int = 8000
    ENVIRONMENT: str = "development"
    SENTRY_DSN: str = ""
    SENTRY_RELEASE: str = "0.1.0"
    API_PREFIX: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="USERS_"  # Prefisso di tutte le variabili (es. TEMPLATE_DATABASE_URL)
    )


settings = Settings()
