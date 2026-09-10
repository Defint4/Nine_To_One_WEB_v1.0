"""Fabriques d'états de jeu pour les tests du moteur du Goulag."""

from __future__ import annotations

import random

from app.games.goulag.engine import Card, GameState, GameStatus, Phase, PlayerState, Suit

H, D, C, S = Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS, Suit.SPADES


def card(value: int, suit: Suit = S) -> Card:
    return Card(value, suit)


def player(
    name: str,
    lives: list[Card],
    defense: Card,
    charges: list[Card] | None = None,
    finish_rank: int | None = None,
) -> PlayerState:
    return PlayerState(
        name=name,
        lives=list(lives),
        defense=defense,
        charges=list(charges or []),
        ready=True,
        finish_rank=finish_rank,
    )


def playing_state(
    players: list[PlayerState],
    draw: list[Card] | None = None,
    discard: list[Card] | None = None,
    turn: int = 0,
    seed: int = 0,
) -> GameState:
    """Partie en cours ; `draw` du fond vers le dessus (la dernière est piochée en premier)."""
    state = GameState(
        players=players,
        draw_pile=list(draw or []),
        discard=list(discard or []),
        status=GameStatus.PLAYING,
        turn_index=turn,
        phase=Phase.ACTION,
        rng=random.Random(seed),
    )
    return state


def total_cards(state: GameState) -> int:
    """Toutes les cartes, y compris celle en main pendant le choix de la cible."""
    return (
        sum(p.card_count for p in state.players)
        + len(state.draw_pile)
        + len(state.discard)
        + (1 if state.drawn else 0)
    )
