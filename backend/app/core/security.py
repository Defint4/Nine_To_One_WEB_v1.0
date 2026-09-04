import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings


def create_player_token(player_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(player_id),
        "iat": now,
        "exp": now + timedelta(days=settings.player_token_days),
        "type": "player",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_player_token(token: str) -> uuid.UUID:
    """Renvoie le player_id. Lève jwt.InvalidTokenError si invalide, expiré ou du mauvais type."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )
    if payload.get("type") != "player":
        raise jwt.InvalidTokenError("wrong token type")
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise jwt.InvalidTokenError("malformed subject") from exc
