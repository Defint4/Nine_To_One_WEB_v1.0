"""Fabriques d'états de jeu pour les tests du moteur."""

from __future__ import annotations

from app.engine import Card, Constraint, GameState, GameStatus, PlayerState, Suit

SUITS = list(Suit)


def cards(*values: int) -> list[Card]:
    """Crée des cartes en variant les couleurs pour éviter les doublons exacts."""
    counts: dict[int, int] = {}
    out = []
    for v in values:
        i = counts.get(v, 0)
        counts[v] = i + 1
        out.append(Card(v, SUITS[i]))
    return out


def playing_state(
    hands: list[list[Card]],
    face_up: list[list[Card]] | None = None,
    face_down: list[list[Card]] | None = None,
    draw: list[Card] | None = None,
    pile: list[Card] | None = None,
    turn: int = 0,
    last_play: int | None = None,
    constraint: Constraint | None = None,
    chase_armed: bool = False,
) -> GameState:
    """Partie en cours avec des mains arbitraires (zones absentes = vides)."""
    players = [
        PlayerState(
            name=f"P{i}",
            hand=list(hand),
            face_up=list(face_up[i]) if face_up else [],
            face_down=list(face_down[i]) if face_down else [],
            ready=True,
        )
        for i, hand in enumerate(hands)
    ]
    return GameState(
        players=players,
        draw_pile=list(draw or []),
        pile=list(pile or []),
        status=GameStatus.PLAYING,
        turn_index=turn,
        last_play_index=last_play,
        constraint=constraint,
        chase_armed=chase_armed,
    )
