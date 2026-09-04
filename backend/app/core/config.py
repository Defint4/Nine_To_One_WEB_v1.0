from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:3003"]

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    # Pas de compte ni mot de passe : le jeton identifie un pseudo sur un appareil,
    # il vit longtemps pour que les habitués rentrent en un tap.
    player_token_days: int = 365

    # Une partie sans aucun joueur connecté pendant ce délai est supprimée.
    empty_room_ttl_minutes: int = 15

    # Journal des parties jouées contre des bots (une ligne JSON par manche) ; vide = désactivé.
    games_log_path: str = "logs/games.jsonl"

    # Bot Difficile : temps de réflexion par coup (s) et nombre de réflexions simultanées.
    # À baisser sur une petite machine : chaque réflexion occupe un cœur à plein.
    bot_time_budget: float = 0.8
    bot_threads: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
