from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URI: str
    DB_NAME: str = "appdb"
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 1440
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "Admin@12345"
    ADMIN_NAME: str = "Super Admin"
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
