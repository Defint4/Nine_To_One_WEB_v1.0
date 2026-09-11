import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
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


@dataclass
class LeaderboardEntry:
    rank: int
    id: uuid.UUID
    pseudo: str
    avatar: str
    played: int
    won: int
    lost: int


@dataclass
class LeaderboardPage:
    total: int
    entries: list[LeaderboardEntry]
    # Position du joueur demandé (`me`), None s'il n'est pas classé.
    me: LeaderboardEntry | None


def _ranking(game: str | None):
    """Le classement complet, numéroté : un jeu (slug) ou tous les jeux cumulés.

    Victoires d'abord ; à victoires égales, celui qui a eu besoin de moins de
    parties passe devant ; le pseudo départage le reste pour un ordre stable.
    """
    totals = (
        select(
            Player.id.label("id"),
            Player.pseudo_key.label("pseudo_key"),
            Player.pseudo.label("pseudo"),
            Player.avatar.label("avatar"),
            func.sum(PlayerGameStats.played).label("played"),
            func.sum(PlayerGameStats.won).label("won"),
            func.sum(PlayerGameStats.lost).label("lost"),
        )
        .join(PlayerGameStats, PlayerGameStats.player_id == Player.id)
        .group_by(Player.id)
    )
    if game is not None:
        totals = totals.where(PlayerGameStats.game == game)
    totals = totals.subquery("totals")
    rank = func.row_number().over(
        order_by=(totals.c.won.desc(), totals.c.played.asc(), totals.c.pseudo_key.asc())
    )
    return select(totals, rank.label("rank")).subquery("ranking")


async def leaderboard(
    db: AsyncSession, game: str | None, offset: int, limit: int, me: str | None
) -> LeaderboardPage:
    ranking = _ranking(game)
    total = await db.scalar(select(func.count()).select_from(ranking))
    rows = await db.execute(select(ranking).order_by(ranking.c.rank).offset(offset).limit(limit))
    mine = None
    if me is not None:
        row = (await db.execute(select(ranking).where(ranking.c.pseudo_key == me.lower()))).first()
        if row is not None:
            mine = _entry(row)
    return LeaderboardPage(total=total or 0, entries=[_entry(r) for r in rows], me=mine)


def _entry(row) -> LeaderboardEntry:
    return LeaderboardEntry(
        rank=row.rank,
        id=row.id,
        pseudo=row.pseudo,
        avatar=row.avatar,
        played=row.played,
        won=row.won,
        lost=row.lost,
    )
