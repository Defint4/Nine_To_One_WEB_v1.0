"""Vue filtrée du Goulag : chaque joueur ne reçoit que ce qu'il a le droit de voir.

Publiques : vies et défense de tous (posées face visible), nombre de charges de
chacun, dessus de la défausse, tailles des piles, phase du tour et action annoncée.
Privée : la carte du dessus pour l'œil de faucon.
Jamais envoyées : les charges (personne ne les voit, pas même leur propriétaire),
le contenu de la pioche.
"""

from __future__ import annotations

from app.games.goulag.engine import GameStatus, Phase, can_charge, peek
from app.rooms.manager import Room


def game_view(room: Room, seat_index: int) -> dict:
    state = room.state
    playing = state.status is GameStatus.PLAYING
    your_turn = playing and state.turn_index == seat_index and state.phase is not Phase.REVIVAL
    you = state.players[seat_index]

    players = [
        {
            "ready": p.ready,
            "finish_rank": p.finish_rank,
            "alive": p.alive,
            "lives": [c.to_dict() for c in p.lives],
            "life_total": p.life_total,
            "defense": p.defense.to_dict() if p.defense else None,
            "charges": len(p.charges),
            "hawk_eye": p.hawk_eye,
        }
        for p in state.players
    ]

    top = peek(state, seat_index) if your_turn else None
    return {
        "phase": state.phase.value if playing else None,
        "pending_action": state.pending_action.value if state.pending_action else None,
        # Œil de faucon : la carte du dessus avant d'annoncer, pour le seul joueur concerné.
        "peek": top.to_dict() if top else None,
        "reviving": state.reviving,
        "draw_count": len(state.draw_pile),
        "discard_count": len(state.discard),
        "discard_top": state.discard[-1].to_dict() if state.discard else None,
        "players": players,
        "can_charge": your_turn and state.phase is Phase.ACTION and can_charge(state, seat_index),
        "must_choose_suit": playing
        and state.phase is Phase.REVIVAL
        and state.reviving == seat_index,
        "alive_count": len(state.alive_indices()) if playing else len(state.players),
        "you_alive": you.alive,
    }
