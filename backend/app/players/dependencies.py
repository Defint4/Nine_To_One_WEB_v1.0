import uuid

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_player_token
from app.players import service
from app.players.models import Player

_bearer = HTTPBearer(auto_error=False)


def get_player_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> uuid.UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Jeton manquant.")
    try:
        return decode_player_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré.") from None


async def get_current_player(
    player_id: uuid.UUID = Depends(get_player_id),
    db: AsyncSession = Depends(get_db),
) -> Player:
    player = await service.get_player(db, player_id)
    if player is None:
        raise HTTPException(status_code=401, detail="Profil introuvable.")
    return player
