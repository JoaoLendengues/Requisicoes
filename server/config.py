from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./requisicoes.db"
    DATABASE_TYPE: Literal["sqlite", "oracle", "postgresql"] = "sqlite"

    SECRET_KEY: str = "mude-esta-chave-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 horas

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    WHATSAPP_API_URL: str = ""
    WHATSAPP_API_KEY: str = ""
    WHATSAPP_INSTANCE: str = ""

    SHARED_FOLDER_PATH: str = "./arquivos"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
