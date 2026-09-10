import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.players.models import Player, PlayerGameStats


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
    db: AsyncSession,
    game: str,
    player_ids: list[uuid.UUID],
    winner_id: uuid.UUID,
    loser_id: uuid.UUID,
) -> None:
    """Stats de fin de partie sur ce jeu : tous ont joué, un gagnant, un perdant."""
    existing = {
        s.player_id: s
        for s in await db.scalars(
            select(PlayerGameStats).where(
                PlayerGameStats.game == game, PlayerGameStats.player_id.in_(player_ids)
            )
        )
    }
    for player_id in player_ids:
        stats = existing.get(player_id)
        if stats is None:
            # Valeurs explicites : les `default` de colonne ne s'appliquent qu'à l'INSERT.
            stats = PlayerGameStats(player_id=player_id, game=game, played=0, won=0, lost=0)
            db.add(stats)
        stats.played += 1
        if player_id == winner_id:
            stats.won += 1
        if player_id == loser_id:
            stats.lost += 1
    await db.commit()
