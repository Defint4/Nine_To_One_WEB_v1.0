"""Mort, choix de la couleur, seconde chance, élimination, fin de partie."""

import pytest

from app.games.goulag.engine import (
    Action,
    GameStatus,
    InvalidAction,
    NotYourTurn,
    Phase,
    Suit,
    announce,
    choose_suit,
    choose_target,
)
from app.games.goulag.tests.helpers import C, D, H, S, card, player, playing_state, total_cards


def lethal_state(draw, players=None, turn=1):
    """P1 (au trait) tue P0 (vies 2 + 1, défense 1) avec la carte du dessus."""
    return playing_state(
        players
        or [
            player("P0", [card(2, H), card(1, D)], card(1, S), charges=[card(4, C)]),
            player("P1", [card(9, C), card(8, H)], card(7, D)),
            player("P2", [card(9, S), card(8, S)], card(6, S)),
        ],
        draw=draw,
        turn=turn,
    )


def kill(state):
    announce(state, 1, Action.ATTACK)
    return choose_target(state, 1, 0)


def test_death_pauses_the_game_for_the_dead_player():
    state = lethal_state([card(5, H), card(13, C)])
    events = kill(state)
    assert events[-1] == {"type": "died", "player": 0}
    assert state.phase is Phase.REVIVAL and state.reviving == 0
    assert state.players[0].lives == [] and state.players[0].alive
    assert card(2, H) in state.discard and card(1, D) in state.discard
    with pytest.raises(NotYourTurn):
        choose_suit(state, 1, Suit.HEARTS)
    with pytest.raises(InvalidAction):
        announce(state, 2, Action.CHARGE)


def test_first_flip_matching_suit_revives_with_that_card():
    state = lethal_state([card(3, D), card(5, H), card(13, C)])
    kill(state)
    events = choose_suit(state, 0, Suit.HEARTS)
    flip = next(e for e in events if e["type"] == "revival_flip")
    assert flip["attempt"] == 1 and flip["success"]
    assert state.players[0].lives == [card(5, H)]
    assert state.players[0].defense == card(1, S)  # la défense reste
    assert state.players[0].charges == []  # perdues dès que l'attaque a touché les vies
    assert card(4, C) in state.discard
    assert state.phase is Phase.ACTION
    assert state.turn_index == 2  # le voisin de l'attaquant, personne ne saute
    assert events[-1] == {"type": "turn", "player": 2}


def test_second_chance_cuts_the_deck_and_takes_the_middle():
    # Pioche (fond → dessus) : 3♦ 7♣ 9♥ 5♥ | 13♣ (carte d'attaque). Après l'attaque il
    # reste 4 cartes ; le premier retournement prend 5♥ (raté), il en reste 3 :
    # la carte du milieu est 7♣.
    state = lethal_state([card(3, D), card(7, C), card(9, H), card(5, H), card(13, C)])
    kill(state)
    events = choose_suit(state, 0, Suit.CLUBS)
    flips = [e for e in events if e["type"] == "revival_flip"]
    assert flips[0]["success"] is False and flips[1]["success"] is True
    assert state.players[0].lives == [card(7, C)]
    assert card(5, H) in state.discard


def test_two_failures_eliminate_and_discard_charges():
    state = lethal_state([card(3, D), card(7, C), card(9, H), card(5, C), card(13, C)])
    kill(state)
    events = choose_suit(state, 0, Suit.SPADES)
    assert events[-2] == {"type": "eliminated", "player": 0, "rank": 3}
    assert events[-1] == {"type": "turn", "player": 2}
    p = state.players[0]
    assert not p.alive and p.lives == [] and p.charges == []
    assert card(4, C) in state.discard
    assert state.status is GameStatus.PLAYING
    assert total_cards(state) == 5 + 4 + 3 + 3  # rien ne disparaît


def test_last_survivor_wins():
    state = lethal_state(
        [card(3, D), card(9, H), card(5, C), card(13, C)],
        players=[
            player("P0", [card(2, H), card(1, D)], card(1, S)),
            player("P1", [card(9, C), card(8, H)], card(7, D)),
        ],
    )
    kill(state)
    events = choose_suit(state, 0, Suit.SPADES)
    assert events[-1]["type"] == "game_over"
    assert state.status is GameStatus.FINISHED
    assert [p.finish_rank for p in state.players] == [2, 1]


def test_eliminated_players_are_skipped_in_turn_order():
    state = lethal_state([card(3, D), card(9, H), card(5, C), card(13, C)])
    kill(state)
    choose_suit(state, 0, Suit.SPADES)  # P0 éliminé, au tour de P2
    assert state.turn_index == 2
    state.draw_pile = [card(2, C)]
    state.discard.append(card(6, H))
    announce(state, 2, Action.CHARGE)
    assert state.turn_index == 1  # P0 sauté


def test_dead_player_cannot_be_targeted():
    state = lethal_state([card(3, D), card(9, H), card(5, C), card(13, C), card(11, S)])
    # Le 11♠ est pioché par P1 d'abord ? Non : P1 attaque avec le dessus (11♠) et tue P0.
    kill(state)
    choose_suit(state, 0, Suit.DIAMONDS)  # 13♣ raté, milieu raté → éliminé
    assert not state.players[0].alive
    state.turn_index = 2
    announce(state, 2, Action.ATTACK)
    with pytest.raises(InvalidAction):
        choose_target(state, 2, 0)


def test_draw_pile_refills_from_discard_when_last_card_is_drawn():
    state = playing_state(
        [
            player("P0", [card(10, H), card(6, D)], card(5, S)),
            player("P1", [card(9, C), card(8, H)], card(7, D)),
        ],
        draw=[card(2, C)],
        discard=[card(3, H), card(4, H), card(12, S)],
    )
    events = announce(state, 0, Action.CHARGE)
    assert events[0] == {"type": "deck_reshuffled", "count": 3}
    assert len(state.draw_pile) == 3 and state.discard == []
