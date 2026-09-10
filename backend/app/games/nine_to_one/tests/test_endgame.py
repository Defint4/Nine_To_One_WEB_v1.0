"""Phases finales (cartes visibles puis cachées), fins de partie, sérialisation."""

import pytest

from app.games.nine_to_one.engine import (
    GameState,
    GameStatus,
    InvalidAction,
    flip_face_down,
    play_cards,
)
from app.games.nine_to_one.tests.helpers import cards, playing_state


def test_face_up_becomes_hand_when_hand_and_draw_empty():
    state = playing_state(
        [cards(8), cards(9, 10, 11)],
        face_up=[cards(5, 12, 3), []],
        pile=cards(4),
    )
    play_cards(state, 0, 8)
    assert sorted(c.value for c in state.players[0].hand) == [3, 5, 12]
    assert state.players[0].face_up == []


def test_face_up_stays_while_draw_pile_remains():
    state = playing_state(
        [cards(8), cards(9, 10, 11)],
        face_up=[cards(5, 12, 3), []],
        draw=cards(6, 7, 13),
    )
    play_cards(state, 0, 8)
    assert len(state.players[0].hand) == 3  # repioché, pas les cartes visibles
    assert len(state.players[0].face_up) == 3


def test_flip_playable_card_stays_in_hand():
    state = playing_state([[], cards(9)], face_down=[cards(12), []], pile=cards(5), turn=0)
    flip_face_down(state, 0, 0)
    assert [c.value for c in state.players[0].hand] == [12]
    assert state.turn_index == 0  # à lui de la jouer
    play_cards(state, 0, 12)
    assert state.pile[-1].value == 12


def test_flip_unplayable_card_forces_pickup():
    state = playing_state(
        [[], cards(9)], face_down=[cards(3), []], pile=cards(13), turn=0, last_play=1
    )
    events = flip_face_down(state, 0, 0)
    assert {"type": "pile_picked_up", "player": 0} in events
    assert sorted(c.value for c in state.players[0].hand) == [3, 13]
    assert state.turn_index == 1  # celui qui avait posé le roi rejoue


def test_flip_forbidden_while_hand_not_empty():
    state = playing_state([cards(5)], face_down=[cards(3)])
    with pytest.raises(InvalidAction):
        flip_face_down(state, 0, 0)


def test_finished_player_gets_rank_and_is_skipped():
    state = playing_state([cards(5), cards(6, 7, 8), cards(9, 10, 11)])
    events = play_cards(state, 0, 5)
    assert state.players[0].finish_rank == 1
    assert {"type": "player_finished", "player": 0, "rank": 1} in events
    assert state.turn_index == 1
    play_cards(state, 1, 6)
    assert state.turn_index == 2  # P0 fini : on saute de P2 à P1 sans repasser par P0
    play_cards(state, 2, 9)
    assert state.turn_index == 1


def test_last_player_with_cards_loses():
    state = playing_state([cards(5), cards(6, 7, 8)])
    events = play_cards(state, 0, 5)
    assert state.status is GameStatus.FINISHED
    assert {"type": "game_over", "loser": 1} in events
    assert state.players[0].finish_rank == 1
    assert state.players[1].finish_rank == 2


def test_finishing_with_a_ten_does_not_replay():
    state = playing_state([cards(10), cards(6, 7, 8), cards(9, 11, 12)], pile=cards(4))
    play_cards(state, 0, 10)
    assert state.players[0].finished
    assert state.turn_index == 1


def test_pickup_replay_skips_finished_blocker():
    # P0 termine avec un roi ; P1 bloqué ramasse. P0 étant fini, le tour reprend
    # dans le sens horaire après lui : P1 joue sur tas vide.
    state = playing_state([cards(13), cards(4, 5, 6), cards(9, 11, 12)])
    play_cards(state, 0, 13)
    assert state.players[0].finished
    assert state.pile == []
    assert state.turn_index == 1


def test_serialization_roundtrip():
    state = playing_state(
        [cards(5, 7), cards(6)],
        face_up=[cards(8), cards(9)],
        face_down=[cards(10), cards(11)],
        draw=cards(3, 4),
        pile=cards(4),
        last_play=1,
    )
    data = state.to_dict()
    restored = GameState.from_dict(data)
    assert restored.to_dict() == data
    play_cards(restored, 0, 5)  # l'état restauré reste jouable
