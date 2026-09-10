"""Registre en mémoire des tables en cours, tous jeux confondus.

Les tables sont éphémères : elles vivent en RAM (un seul worker uvicorn), seules
les stats des joueurs sont persistées en base à la fin. Une table sans aucun
joueur connecté pendant empty_room_ttl_minutes est supprimée par cleanup_loop.

La plateforme possède la table (sièges, sockets, chat, timer, revanche) ; l'état
du jeu (`state`) et ses données annexes (`data`) appartiennent à la GameSpec.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import WebSocket

from app.core.config import settings
from app.games.base import GameSpec, GameStatus

logger = logging.getLogger(__name__)

CHAT_HISTORY_SIZE = 100


@dataclass
class Seat:
    """Un joueur assis à la table ; l'index du siège == l'index du joueur dans l'état du jeu."""

    player_id: uuid.UUID
    pseudo: str
    avatar: str
    socket: WebSocket | None = None
    # Difficulté du bot qui occupe ce siège (clé de GameSpec.bot_difficulties), None pour un humain.
    bot: str | None = None


@dataclass
class Room:
    code: str
    spec: GameSpec
    state: Any
    seats: list[Seat] = field(default_factory=list)
    data: Any = None  # propriété du jeu (voir GameSpec.new_room_data)
    chat: list[dict] = field(default_factory=list)
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stats_recorded: bool = False
    # Timer de tour (choisi par le créateur en lobby ; 0 = sans limite).
    turn_seconds: int = 0
    turn_deadline: float | None = None  # time.monotonic() de l'échéance
    turn_token: int = 0  # invalide les timers programmés quand un coup est joué
    # Table de revanche déjà créée depuis cette partie, le cas échéant.
    rematch_code: str | None = None
    # Jeton invalidant les actions de bots programmées dès qu'un coup survient.
    bot_token: int = 0

    @property
    def game(self) -> str:
        return self.spec.slug

    @property
    def status(self) -> GameStatus:
        return self.spec.status(self.state)

    def touch(self) -> None:
        self.last_activity = datetime.now(UTC)

    def seat_of(self, player_id: uuid.UUID) -> int | None:
        for i, seat in enumerate(self.seats):
            if seat.player_id == player_id:
                return i
        return None

    def connected_count(self) -> int:
        """Humains connectés (les bots ne retiennent pas une table en vie)."""
        return sum(1 for seat in self.seats if seat.socket is not None)

    def human_count(self) -> int:
        return sum(1 for seat in self.seats if seat.bot is None)

    def add_chat(self, message: dict) -> None:
        self.chat.append(message)
        del self.chat[:-CHAT_HISTORY_SIZE]

    def humans_first(self) -> None:
        """Le siège 0 est le créateur : si un humain est parti, un humain doit
        rester en tête (pas un bot). Rotation commune des sièges et des joueurs."""
        k = next((i for i, s in enumerate(self.seats) if s.bot is None), None)
        if not k:
            return
        self.seats[:] = self.seats[k:] + self.seats[:k]
        self.spec.rotate_players(self.state, k)


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def create(self, spec: GameSpec, creator: Seat) -> Room:
        code = self._unique_code()
        room = Room(
            code=code,
            spec=spec,
            state=spec.create_state(creator.pseudo),
            seats=[creator],
            data=spec.new_room_data(),
        )
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code)

    def delete(self, code: str) -> None:
        self.rooms.pop(code, None)

    def open_rooms(self, game: str | None = None) -> list[Room]:
        """Tables encore en lobby, rejoignables (filtrées par jeu si demandé)."""
        return [
            r
            for r in self.rooms.values()
            if r.status is GameStatus.LOBBY and (game is None or r.game == game)
        ]

    def _unique_code(self) -> str:
        while True:
            code = f"{random.randint(0, 9999):04d}"
            if code not in self.rooms:
                return code

    async def cleanup_loop(self, on_delete: Callable[[str], Awaitable[None]] | None = None) -> None:
        """Supprime les tables fantômes (0 connecté depuis empty_room_ttl_minutes).

        `on_delete(game)` est appelé pour chaque jeu touché (liste des tables en direct).
        """
        ttl = timedelta(minutes=settings.empty_room_ttl_minutes)
        while True:
            await asyncio.sleep(60)
            now = datetime.now(UTC)
            touched: set[str] = set()
            for code, room in list(self.rooms.items()):
                if room.connected_count() == 0 and now - room.last_activity > ttl:
                    self.delete(code)
                    touched.add(room.game)
            if on_delete is not None:
                for game in touched:
                    await on_delete(game)


manager = RoomManager()
