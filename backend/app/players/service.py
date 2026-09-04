import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.players.models import Player


async def enter(db: AsyncSession, pseudo: str, avatar: str) -> Player:
    """Récupère le profil lié au pseudo (insensible à la casse) ou le crée.

    Pas de mot de passe : le pseudo suffit à reprendre son profil, choix assumé
    pour un jeu entre amis. L'avatar est mis à jour à chaque entrée.
    """
    key = pseudo.lower()
    player = await db.scalar(select(Player).where(Player.pseudo_key == key))
    if player is None:
        player = Player(pseudo_key=key, pseudo=pseudo, avatar=avatar)
        db.add(player)
    else:
        player.pseudo = pseudo
        player.avatar = avatar
    await db.commit()
    await db.refresh(player)
    return player


async def get_player(db: AsyncSession, player_id: uuid.UUID) -> Player | None:
    return await db.get(Player, player_id)


async def record_game_results(
    db: AsyncSession, player_ids: list[uuid.UUID], winner_id: uuid.UUID, loser_id: uuid.UUID
) -> None:
    """Stats de fin de partie : tous ont joué, le 1er sorti gagne, le dernier perd."""
    result = await db.scalars(select(Player).where(Player.id.in_(player_ids)))
    for player in result:
        player.games_played += 1
        if player.id == winner_id:
            player.games_won += 1
        if player.id == loser_id:
            player.games_lost += 1
    await db.commit()
