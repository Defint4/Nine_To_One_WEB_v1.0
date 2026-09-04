"""Mise en place : distribution, échanges initiaux, démarrage."""

import pytest

from app.engine import (
    GameStatus,
    InvalidAction,
    add_player,
    create_game,
    new_deck,
    play_cards,
    set_ready,
    swap_cards,
)
from tests.helpers import cards


def test_deck_has_52_unique_cards():
    deck = new_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52
    assert {c.value for c in deck} == set(range(2, 15))


def test_create_deals_three_zones_of_three():
    state = create_game("alice", seed=1)
    p = state.players[0]
    assert (len(p.hand), len(p.face_up), len(p.face_down)) == (3, 3, 3)
    assert len(state.draw_pile) == 52 - 9
    assert state.status is GameStatus.LOBBY


def test_add_player_deals_and_limits():
    state = create_game("alice", seed=1)
    for name in ["bob", "carl", "dan", "eve"]:
        add_player(state, name)
    assert len(state.draw_pile) == 52 - 5 * 9
    with pytest.raises(InvalidAction):
        add_player(state, "frank")  # partie pleine (5 max)
    with pytest.raises(InvalidAction):
        state.players.pop()
        add_player(state, "alice")  # pseudo déjà pris


def test_swap_exchanges_hand_and_face_up():
    state = create_game("alice", seed=1)
    hand_card = state.players[0].hand[0]
    face_card = state.players[0].face_up[2]
    swap_cards(state, 0, 0, 2)
    assert face_card in state.players[0].hand  # la main est retriée après l'échange
    assert state.players[0].face_up[2] == hand_card


def test_hand_always_sorted():
    state = create_game("alice", seed=1)
    values = [c.value for c in state.players[0].hand]
    assert values == sorted(values)
    swap_cards(state, 0, 0, 0)
    values = [c.value for c in state.players[0].hand]
    assert values == sorted(values)


def test_swap_blocked_once_ready():
    state = create_game("alice", seed=1)
    add_player(state, "bob")
    set_ready(state, 0)
    with pytest.raises(InvalidAction):
        swap_cards(state, 0, 0, 0)
    # bob, pas encore prêt, peut toujours échanger
    swap_cards(state, 1, 0, 0)


def test_game_starts_when_all_ready():
    state = create_game("alice", seed=1)
    add_player(state, "bob")
    assert set_ready(state, 0) == []
    events = set_ready(state, 1)
    assert state.status is GameStatus.PLAYING
    assert events[0]["type"] == "game_started"


def test_no_start_with_single_player():
    state = create_game("alice", seed=1)
    set_ready(state, 0)
    assert state.status is GameStatus.LOBBY


def test_lowest_card_holder_starts_two_excluded():
    state = create_game("alice", seed=1)
    add_player(state, "bob")
    state.players[0].hand = cards(2, 9, 13)  # le 2 ne compte pas
    state.players[1].hand = cards(4, 12, 14)
    set_ready(state, 0)
    set_ready(state, 1)
    assert state.turn_index == 1


def test_first_player_plays_whatever_he_wants():
    state = create_game("alice", seed=1)
    add_player(state, "bob")
    state.players[0].hand = cards(3, 9, 13)
    state.players[1].hand = cards(4, 12, 14)
    set_ready(state, 0)
    set_ready(state, 1)
    assert state.turn_index == 0  # il a le 3, mais rien ne l'oblige à le jouer
    play_cards(state, 0, 13)
    assert state.pile[-1].value == 13
