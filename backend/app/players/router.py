from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import create_player_token
from app.players import service
from app.players.dependencies import get_current_player
from app.players.models import Player
from app.players.schemas import EnterRequest, EnterResponse, PlayerOut

router = APIRouter(prefix="/api/players", tags=["players"])


@router.post("/enter", response_model=EnterResponse)
@limiter.limit("10/minute")
async def enter(
    request: Request, payload: EnterRequest, db: AsyncSession = Depends(get_db)
) -> EnterResponse:
    player = await service.enter(db, payload.pseudo, payload.avatar)
    return EnterResponse(
        player=PlayerOut.model_validate(player), token=create_player_token(player.id)
    )


@router.get("/me", response_model=PlayerOut)
async def me(player: Player = Depends(get_current_player)) -> PlayerOut:
    return PlayerOut.model_validate(player)


@router.get("/by-pseudo/{pseudo}", response_model=PlayerOut)
@limiter.limit("60/minute")
async def by_pseudo(request: Request, pseudo: str, db: AsyncSession = Depends(get_db)) -> PlayerOut:
    """Profil public d'un joueur (stats affichées en tapant son avatar à la table)."""
    player = await db.scalar(select(Player).where(Player.pseudo_key == pseudo.lower()))
    if player is None:
        raise HTTPException(status_code=404, detail="Joueur inconnu.")
    return PlayerOut.model_validate(player)
