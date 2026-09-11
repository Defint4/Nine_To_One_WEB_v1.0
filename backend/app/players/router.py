from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import create_player_token
from app.games.registry import get_game
from app.players import service
from app.players.dependencies import get_current_player
from app.players.models import Player
from app.players.schemas import EnterRequest, EnterResponse, LeaderboardOut, PlayerOut

router = APIRouter(prefix="/api/players", tags=["players"])


@router.post("/enter", response_model=EnterResponse)
@limiter.limit("10/minute")
async def enter(
    request: Request, payload: EnterRequest, db: AsyncSession = Depends(get_db)
) -> EnterResponse:
    player = await service.enter(db, payload.pseudo, payload.avatar)
    return EnterResponse(player=PlayerOut.from_player(player), token=create_player_token(player.id))


@router.get("/me", response_model=PlayerOut)
async def me(player: Player = Depends(get_current_player)) -> PlayerOut:
    return PlayerOut.from_player(player)


@router.get("/leaderboard", response_model=LeaderboardOut)
@limiter.limit("60/minute")
async def leaderboard(
    request: Request,
    game: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    me: str | None = Query(None, max_length=20),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardOut:
    """Classement d'un jeu (slug) ou de tous les jeux cumulés, page par page."""
    if game is not None and get_game(game) is None:
        raise HTTPException(status_code=404, detail="Jeu inconnu.")
    page = await service.leaderboard(db, game, offset, limit, me)
    return LeaderboardOut.model_validate(page)


@router.get("/by-pseudo/{pseudo}", response_model=PlayerOut)
@limiter.limit("60/minute")
async def by_pseudo(request: Request, pseudo: str, db: AsyncSession = Depends(get_db)) -> PlayerOut:
    """Profil public d'un joueur (stats affichées en tapant son avatar à la table)."""
    player = await db.scalar(select(Player).where(Player.pseudo_key == pseudo.lower()))
    if player is None:
        raise HTTPException(status_code=404, detail="Joueur inconnu.")
    return PlayerOut.from_player(player)
