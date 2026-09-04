import re
import uuid

from pydantic import BaseModel, Field, field_validator

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


class PlayerOut(BaseModel):
    id: uuid.UUID
    pseudo: str
    avatar: str
    games_played: int
    games_won: int
    games_lost: int

    model_config = {"from_attributes": True}


class EnterResponse(BaseModel):
    player: PlayerOut
    token: str
