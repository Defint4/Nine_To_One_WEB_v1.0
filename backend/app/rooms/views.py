"""Vues filtrées de l'état du jeu : chaque joueur ne reçoit que ce qu'il a le droit de voir.

Publiques : tas central, tailles de pioche/défausse, cartes visibles de tous,
nombre de cartes des adversaires. Privées : sa propre main. Jamais envoyées :
les mains adverses, les cartes cachées, le contenu de la pioche.
"""

from __future__ import annotations

import time

from app.engine import GameStatus, chase_value, playable_values
from app.rooms.manager import Room


def room_view(room: Room, seat_index: int) -> dict:
    state = room.state
    is_playing = state.status is GameStatus.PLAYING
    your_turn = is_playing and state.turn_index == seat_index
    you = state.players[seat_index]

    players = []
    for i, seat in enumerate(room.seats):
        p = state.players[i]
        players.append(
            {
                "seat": i,
                "pseudo": seat.pseudo,
                "avatar": seat.avatar,
                "connected": seat.socket is not None or seat.bot is not None,
                "bot": seat.bot,
                "ready": p.ready,
                "finish_rank": p.finish_rank,
                "hand_count": len(p.hand),
                "face_up": [c.to_dict() for c in p.face_up],
                "face_down_count": len(p.face_down),
                "hand": [c.to_dict() for c in p.hand] if i == seat_index else None,
            }
        )

    return {
        "code": room.code,
        "status": state.status.value,
        "your_seat": seat_index,
        "turn": state.turn_index if is_playing else None,
        "constraint": state.constraint.to_dict() if state.constraint else None,
        "required_first_value": state.required_first_value,
        "pile": [c.to_dict() for c in state.pile],
        "draw_count": len(state.draw_pile),
        "discard_count": len(state.discard),
        "players": players,
        "playable_values": sorted(playable_values(state, seat_index)) if your_turn else [],
        "must_flip": your_turn and not you.hand,
        # Qui a posé en dernier, et la valeur enchaînable en « bonne pioche » (le
        # serveur est seul juge : carte fraîchement piochée ou cachée à retourner).
        "last_play_seat": state.last_play_index,
        "chase_value": chase_value(state, seat_index),
        "turn_seconds": room.turn_seconds,
        # Temps restant calculé côté serveur : insensible à l'horloge du client.
        "turn_remaining": (
            max(0.0, round(room.turn_deadline - time.monotonic(), 1))
            if is_playing and room.turn_seconds and room.turn_deadline is not None
            else None
        ),
        "stats": {"moves": room.moves, "pickups": {str(k): v for k, v in room.pickups.items()}},
    }
