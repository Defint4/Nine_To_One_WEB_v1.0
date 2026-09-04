"""Registre en mémoire des parties en cours.

Les parties sont éphémères : elles vivent en RAM (un seul worker uvicorn), seules
les stats des joueurs sont persistées en base à la fin. Une partie sans aucun
joueur connecté pendant empty_room_ttl_minutes est supprimée par cleanup_loop.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import WebSocket

from app.core.config import settings
from app.engine import GameState, GameStatus

logger = logging.getLogger(__name__)

CHAT_HISTORY_SIZE = 100


@dataclass
class Seat:
    """Un joueur assis à la table ; l'index du siège == l'index dans GameState.players."""

    player_id: uuid.UUID
    pseudo: str
    avatar: str
    socket: WebSocket | None = None
    # Difficulté du bot qui occupe ce siège ("easy" | "normal" | "hard"), None pour un humain.
    bot: str | None = None


@dataclass
class Room:
    code: str
    state: GameState
    seats: list[Seat] = field(default_factory=list)
    chat: list[dict] = field(default_factory=list)
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stats_recorded: bool = False
    # Timer de tour (choisi par le créateur en lobby ; 0 = sans limite).
    turn_seconds: int = 0
    turn_deadline: float | None = None  # time.monotonic() de l'échéance
    turn_token: int = 0  # invalide les timers programmés quand un coup est joué
    # Statistiques de la manche en cours (pour l'écran de fin).
    moves: int = 0
    pickups: dict[int, int] = field(default_factory=dict)
    # Table de revanche déjà créée depuis cette partie, le cas échéant.
    rematch_code: str | None = None
    # Bots : jeton invalidant les coups programmés, mémoire des événements publics.
    bot_token: int = 0
    bot_memory: object | None = None
    # Journal de la manche (distribution initiale + événements) pour analyser
    # les parties contre les bots.
    initial_state: dict | None = None
    history: list[dict] = field(default_factory=list)

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


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def create(self, state: GameState, creator: Seat) -> Room:
        code = self._unique_code()
        room = Room(code=code, state=state, seats=[creator])
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code)

    def delete(self, code: str) -> None:
        self.rooms.pop(code, None)

    def open_rooms(self) -> list[Room]:
        """Parties encore en lobby, rejoignables."""
        return [r for r in self.rooms.values() if r.state.status is GameStatus.LOBBY]

    def _unique_code(self) -> str:
        while True:
            code = f"{random.randint(0, 9999):04d}"
            if code not in self.rooms:
                return code

    async def cleanup_loop(self) -> None:
        """Supprime les parties fantômes (0 connecté depuis empty_room_ttl_minutes)."""
        ttl = timedelta(minutes=settings.empty_room_ttl_minutes)
        while True:
            await asyncio.sleep(60)
            now = datetime.now(UTC)
            for code, room in list(self.rooms.items()):
                if room.connected_count() == 0 and now - room.last_activity > ttl:
                    self.delete(code)
                    logger.info("Partie %s supprimée (vide depuis %s)", code, ttl)


manager = RoomManager()
