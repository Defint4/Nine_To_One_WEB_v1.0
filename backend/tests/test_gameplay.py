"""Règles de pose : ordre, cartes spéciales, coupes, ramassages, multiples."""

import pytest

from app.engine import (
    Comparator,
    Constraint,
    IllegalMove,
    NotYourTurn,
    can_play_value,
    play_cards,
)
from tests.helpers import cards, playing_state


def test_must_play_higher_or_equal():
    state = playing_state([cards(5, 8, 11), cards(9)], pile=cards(8))
    with pytest.raises(IllegalMove):
        play_cards(state, 0, 5)
    play_cards(state, 0, 8)  # égal : autorisé
    assert state.pile[-1].value == 8


def test_not_your_turn():
    state = playing_state([cards(5), cards(6)], turn=0)
    with pytest.raises(NotYourTurn):
        play_cards(state, 1, 6)


def test_draw_refills_hand_to_three():
    state = playing_state([cards(5), cards(6, 7, 8)], draw=cards(3, 4, 9, 10))
    play_cards(state, 0, 5)
    assert len(state.players[0].hand) == 3
    assert len(state.draw_pile) == 1


def test_no_draw_when_hand_full():
    state = playing_state([cards(5, 6, 8, 9), cards(6, 7, 8)], draw=cards(3))
    play_cards(state, 0, 5)
    assert len(state.players[0].hand) == 3
    assert len(state.draw_pile) == 1


def test_two_playable_anytime_and_resets():
    state = playing_state([cards(2, 5), cards(3, 6, 7)], pile=cards(13))
    play_cards(state, 0, 2)
    # après un 2, tout est jouable
    play_cards(state, 1, 3)
    assert state.pile[-1].value == 3


def test_seven_requires_direction_choice():
    state = playing_state([cards(7, 5), cards(3)], pile=cards(5))
    with pytest.raises(IllegalMove):
        play_cards(state, 0, 7)


def test_seven_below_constrains_next_player():
    state = playing_state([cards(7, 5), cards(4, 8, 11)], pile=cards(5))
    play_cards(state, 0, 7, direction=Comparator.LTE)
    with pytest.raises(IllegalMove):
        play_cards(state, 1, 8)
    play_cards(state, 1, 4)
    # la contrainte est consommée : on repart sur la règle normale (>= 4)
    assert state.constraint is None


def test_seven_above_constrains_next_player():
    state = playing_state([cards(7, 5), cards(4, 11, 3)], pile=cards(5))
    play_cards(state, 0, 7, direction=Comparator.GTE)
    with pytest.raises(IllegalMove):
        play_cards(state, 1, 4)
    play_cards(state, 1, 11)


def test_seven_playable_on_a_nine():
    state = playing_state([cards(7)], pile=cards(9), constraint=Constraint(Comparator.LTE, 9))
    assert can_play_value(state, 7)


def test_seven_not_playable_on_higher_card():
    state = playing_state([cards(7)], pile=cards(8))
    assert not can_play_value(state, 7)


def test_nine_forces_below():
    state = playing_state([cards(9, 5), cards(3, 10, 11)], pile=cards(6))
    play_cards(state, 0, 9)
    with pytest.raises(IllegalMove):
        play_cards(state, 1, 11)
    with pytest.raises(IllegalMove):
        play_cards(state, 1, 10)  # le 10 est bloqué quand il faut jouer en dessous
    play_cards(state, 1, 3)


def test_nine_blocked_under_seven_below():
    state = playing_state([cards(9)], constraint=Constraint(Comparator.LTE, 7), pile=cards(7))
    assert not can_play_value(state, 9)


def test_ten_cuts_pile_and_replays():
    state = playing_state([cards(10, 5), cards(6)], pile=cards(4, 12, 14))
    play_cards(state, 0, 10)
    assert state.pile == []
    assert len(state.discard) == 4
    assert state.constraint is None
    assert state.turn_index == 0  # le joueur rejoue


def test_ten_playable_on_any_higher_card():
    state = playing_state([cards(10)], pile=cards(14))
    assert can_play_value(state, 10)


def test_four_in_a_row_cuts_and_replays():
    state = playing_state([cards(8, 5), cards(6)], pile=cards(3, 8, 8, 8))
    play_cards(state, 0, 8)
    assert state.pile == []
    assert len(state.discard) == 5
    assert state.turn_index == 0


def test_four_in_a_row_with_a_pair():
    state = playing_state([cards(6, 6, 5), cards(9)], pile=cards(6, 6))
    play_cards(state, 0, 6, count=2)
    assert state.pile == []
    assert state.turn_index == 0


def test_play_multiple_identical_cards():
    state = playing_state([cards(11, 11, 5), cards(12)], pile=cards(9, 4))
    play_cards(state, 0, 11, count=2)
    assert [c.value for c in state.pile[-2:]] == [11, 11]
    assert state.turn_index == 1


def test_multiple_requires_enough_copies():
    state = playing_state([cards(11, 5), cards(12)])
    with pytest.raises(IllegalMove):
        play_cards(state, 0, 11, count=2)


def test_blocked_player_picks_up_and_previous_replays():
    state = playing_state([cards(13, 5), cards(4, 6, 3)])
    events = play_cards(state, 0, 13)
    assert {"type": "pile_picked_up", "player": 1} in events
    assert state.pile == []
    assert state.constraint is None
    assert len(state.players[1].hand) == 4  # sa main + le roi ramassé
    assert state.turn_index == 0  # celui qui a bloqué rejoue


def test_pickup_clears_constraint():
    state = playing_state([cards(7, 5), cards(13, 14, 12)], pile=cards(5))
    play_cards(state, 0, 7, direction=Comparator.LTE)
    assert state.turn_index == 0  # P1 a ramassé automatiquement, P0 rejoue
    assert state.constraint is None
    assert len(state.players[1].hand) == 5
