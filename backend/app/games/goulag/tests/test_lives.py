"""Recomposition des cartes de vie après dégâts."""

from app.games.goulag.engine import Action, announce, choose_target
from app.games.goulag.tests.helpers import C, D, H, S, card, player, playing_state, total_cards


def hit(lives, damage_card, draw_extra=(), discard=(), defense=card(0 + 1, S)):
    """P0 (défense 1) encaisse `damage_card` piochée par P1 ; renvoie l'état."""
    state = playing_state(
        [
            player("P0", lives, card(1, S)),
            player("P1", [card(9, C), card(8, H)], card(7, D)),
        ],
        draw=[*draw_extra, damage_card],
        discard=list(discard),
        turn=1,
    )
    announce(state, 1, Action.ATTACK)
    choose_target(state, 1, 0)
    return state


def test_keeps_strongest_and_finds_complement_in_discard_first():
    # 6 + 4 = 10, dégâts 3 (carte 4 contre défense 1) → 7 = 6 + As, l'As vient de la défausse.
    state = hit([card(6, H), card(4, D)], card(4, C), draw_extra=[card(1, C)], discard=[card(1, H)])
    p = state.players[0]
    assert p.lives == [card(6, H), card(1, H)]
    assert p.life_total == 7
    assert card(4, D) in state.discard and card(1, C) in state.draw_pile


def test_complement_taken_from_draw_pile_when_discard_has_none():
    state = hit([card(6, H), card(4, D)], card(4, C), draw_extra=[card(1, C), card(9, S)])
    assert state.players[0].lives == [card(6, H), card(1, C)]
    assert state.players[0].life_total == 7


def test_existing_card_equal_to_new_total_stays_alone():
    # 6 + 4, dégâts 6 → 4 : le 4 reste seul.
    state = hit([card(6, H), card(4, D)], card(7, C))
    assert state.players[0].lives == [card(4, D)]
    assert card(6, H) in state.discard


def test_single_card_when_total_below_strongest():
    # 6 + 4, dégâts 7 → 3 : une seule carte, un 3.
    state = hit([card(6, H), card(4, D)], card(8, C), draw_extra=[card(3, S)])
    assert state.players[0].lives == [card(3, S)]
    assert state.players[0].life_total == 3


def test_two_cards_when_exact_value_is_unavailable():
    # 6 + 4, dégâts 1 → 9 = 6 + 3 ; aucun 3 disponible → 6 + (2 + 1).
    state = hit(
        [card(6, H), card(4, D)],
        card(2, C),
        draw_extra=[card(1, C), card(2, D), card(10, S)],
    )
    p = state.players[0]
    assert p.life_total == 9
    assert len(p.lives) == 3 and p.lives[0] == card(6, H)


def test_all_cards_are_accounted_for_after_recomposition():
    state = hit([card(6, H), card(4, D)], card(4, C), draw_extra=[card(1, C), card(9, S)])
    assert total_cards(state) == 3 + 3 + 1 + 2


def test_single_life_card_recomposes_too():
    state = hit([card(9, H)], card(4, C), draw_extra=[card(6, S)])
    assert state.players[0].lives == [card(6, S)]
    assert state.players[0].life_total == 6
