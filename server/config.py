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

    # Backup do banco de dados
    BACKUP_FOLDER: str = r"\\10.1.1.140\ti\REQUISIÇÕES (VENDAS)\backup_bd"
    BACKUP_RETENTION: int = 15   # número máximo de arquivos por tipo antes de rotacionar
    BACKUP_DAILY_HOUR: int = 2   # hora do backup diário automático (formato 24h)

    # Conexão explícita para pg_dump (evita problemas de parsing da DATABASE_URL)
    BACKUP_DB_HOST: str = "10.1.1.151"
    BACKUP_DB_PORT: int = 5432
    BACKUP_DB_USER: str = "tipinheiro"
    BACKUP_DB_PASSWORD: str = "Pinheiro123"
    BACKUP_DB_NAME: str = "requisicoes"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8-sig"  # suporta arquivos salvos com BOM no Windows


settings = Settings()
