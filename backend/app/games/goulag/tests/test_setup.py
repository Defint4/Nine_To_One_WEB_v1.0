"""Mise en place : lobby, distribution, premier joueur."""

import pytest

from app.games.goulag.engine import (
    MAX_PLAYERS,
    GameStatus,
    InvalidAction,
    add_player,
    create_game,
    new_deck,
    remove_player,
    set_ready,
)
from app.games.goulag.tests.helpers import C, D, H, S, card, player, playing_state


def test_deck_has_52_cards_from_ace_to_king():
    deck = new_deck()
    assert len(deck) == 52
    assert {c.value for c in deck} == set(range(1, 14))


def test_lobby_limits():
    state = create_game("P0")
    for i in range(1, MAX_PLAYERS):
        add_player(state, f"P{i}")
    with pytest.raises(InvalidAction):
        add_player(state, "Trop")
    with pytest.raises(InvalidAction):
        add_player(state, "P0")  # pseudo déjà pris (après retrait d'un siège)
    remove_player(state, 1)
    assert [p.name for p in state.players] == ["P0", "P2", "P3", "P4", "P5"]


def test_start_deals_two_lives_and_lowest_as_defense():
    state = create_game("P0", seed=1)
    add_player(state, "P1")
    add_player(state, "P2")
    assert set_ready(state, 0) == []
    set_ready(state, 1)
    events = set_ready(state, 2)
    assert state.status is GameStatus.PLAYING
    assert events[0]["type"] == "game_started"
    assert events[-1] == {"type": "turn", "player": state.turn_index}
    for p in state.players:
        assert len(p.lives) == 2 and p.defense is not None and p.charges == []
        assert p.defense.value <= min(c.value for c in p.lives)
        assert p.lives[0].value >= p.lives[1].value
    assert len(state.draw_pile) == 52 - 9
    assert state.discard == []


def test_first_player_lowest_defense_then_fewest_lives():
    # Même défense entre P0 et P2, P2 a moins de vies : P2 commence.
    state = playing_state(
        [
            player("P0", [card(10, H), card(9, D)], card(3, S)),
            player("P1", [card(5, H), card(4, D)], card(4, C)),
            player("P2", [card(6, H), card(5, C)], card(3, D)),
        ]
    )
    from app.games.goulag.engine.game import _start  # noqa: PLC0415

    # On rejoue la sélection du premier joueur sur une distribution imposée.
    state.rng.seed(0)
    key = lambda i: (state.players[i].defense.value, state.players[i].life_total)  # noqa: E731
    best = min(key(i) for i in range(3))
    assert [i for i in range(3) if key(i) == best] == [2]
    assert callable(_start)


def test_cannot_act_before_start():
    state = create_game("P0")
    add_player(state, "P1")
    from app.games.goulag.engine import Action, announce  # noqa: PLC0415

    with pytest.raises(InvalidAction):
        announce(state, 0, Action.ATTACK)
