"""Vue d'une table telle qu'envoyée à un siège : socle commun + partie propre au jeu."""

from __future__ import annotations

import time

from app.games.base import GameStatus
from app.rooms.manager import Room


def room_view(room: Room, seat_index: int) -> dict:
    status = room.status
    is_playing = status is GameStatus.PLAYING

    players = [
        {
            "seat": i,
            "pseudo": seat.pseudo,
            "avatar": seat.avatar,
            "connected": seat.socket is not None or seat.bot is not None,
            "bot": seat.bot,
        }
        for i, seat in enumerate(room.seats)
    ]

    view = {
        "code": room.code,
        "game": room.game,
        "status": status.value,
        "your_seat": seat_index,
        "turn": room.spec.current_turn(room.state) if is_playing else None,
        "players": players,
        "turn_seconds": room.turn_seconds,
        # Temps restant calculé côté serveur : insensible à l'horloge du client.
        "turn_remaining": (
            max(0.0, round(room.turn_deadline - time.monotonic(), 1))
            if is_playing and room.turn_seconds and room.turn_deadline is not None
            else None
        ),
    }

    game_view = room.spec.view(room, seat_index)
    for base, extra in zip(players, game_view.pop("players", []), strict=True):
        base.update(extra)
    view.update(game_view)
    return view
