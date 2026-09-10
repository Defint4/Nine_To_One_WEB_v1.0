"""Vue filtrée de Nine to One : chaque joueur ne reçoit que ce qu'il a le droit de voir.

Publiques : tas central, tailles de pioche/défausse, cartes visibles de tous,
nombre de cartes des adversaires. Privées : sa propre main. Jamais envoyées :
les mains adverses, les cartes cachées, le contenu de la pioche.

Les champs communs (code, statut, sièges, timer) sont ajoutés par la plateforme
(app.rooms.views.room_view) ; ici uniquement ce qui est propre au jeu.
"""

from __future__ import annotations

from app.games.nine_to_one.engine import GameStatus, chase_value, playable_values
from app.rooms.manager import Room


def game_view(room: Room, seat_index: int) -> dict:
    state = room.state
    your_turn = state.status is GameStatus.PLAYING and state.turn_index == seat_index
    you = state.players[seat_index]

    players = []
    for i, p in enumerate(state.players):
        players.append(
            {
                "ready": p.ready,
                "finish_rank": p.finish_rank,
                "hand_count": len(p.hand),
                "face_up": [c.to_dict() for c in p.face_up],
                "face_down_count": len(p.face_down),
                "hand": [c.to_dict() for c in p.hand] if i == seat_index else None,
            }
        )

    return {
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
        "stats": {
            "moves": room.data.moves,
            "pickups": {str(k): v for k, v in room.data.pickups.items()},
        },
    }
