import re
import uuid

from pydantic import BaseModel, Field, field_validator

from app.players.models import Player

PSEUDO_PATTERN = r"^[A-Za-z0-9À-ÖØ-öø-ÿ_\- ]{2,20}$"
AVATAR_PATTERN = r"^[a-z0-9\-]{1,40}$"


class EnterRequest(BaseModel):
    pseudo: str = Field(min_length=2, max_length=20)
    avatar: str = Field(pattern=AVATAR_PATTERN)

    @field_validator("pseudo")
    @classmethod
    def normalize_pseudo(cls, value: str) -> str:
        value = " ".join(value.split())  # espaces superflus
        if not re.fullmatch(PSEUDO_PATTERN, value):
            raise ValueError("Pseudo invalide : lettres, chiffres, espaces, - et _ uniquement.")
        return value


class GameStatsOut(BaseModel):
    played: int
    won: int
    lost: int

    model_config = {"from_attributes": True}


class PlayerOut(BaseModel):
    id: uuid.UUID
    pseudo: str
    avatar: str
    # Par jeu (clé = slug) ; un jeu jamais joué n'apparaît pas.
    stats: dict[str, GameStatsOut]

    @classmethod
    def from_player(cls, player: Player) -> "PlayerOut":
        return cls(
            id=player.id,
            pseudo=player.pseudo,
            avatar=player.avatar,
            stats={s.game: GameStatsOut.model_validate(s) for s in player.stats},
        )


class EnterResponse(BaseModel):
    player: PlayerOut
    token: str
