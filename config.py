from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    admin: SecretStr
    telegram_bot_api: SecretStr

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')


info = Settings()
