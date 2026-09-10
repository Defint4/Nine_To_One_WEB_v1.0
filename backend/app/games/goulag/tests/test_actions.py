"""Le tour : annoncer à l'aveugle, cibler, charger, défendre, attaquer."""

import pytest

from app.games.goulag.engine import (
    Action,
    IllegalMove,
    InvalidAction,
    NotYourTurn,
    Phase,
    announce,
    choose_target,
    peek,
)
from app.games.goulag.tests.helpers import C, D, H, S, card, player, playing_state, total_cards


def two_players(draw, **kw):
    return playing_state(
        [
            player("P0", [card(10, H), card(6, D)], card(5, S)),
            player("P1", [card(9, C), card(8, H)], card(7, D)),
        ],
        draw=draw,
        **kw,
    )


def test_only_current_player_in_action_phase():
    state = two_players([card(2, C)])
    with pytest.raises(NotYourTurn):
        announce(state, 1, Action.ATTACK)
    with pytest.raises(InvalidAction):
        choose_target(state, 0, 1)  # rien d'annoncé


def test_charge_is_blind_and_capped_at_two():
    state = two_players([card(2, C), card(3, C), card(4, C), card(5, C)], turn=0)
    events = announce(state, 0, Action.CHARGE)
    assert [e["type"] for e in events] == ["charged", "turn"]
    assert state.players[0].charges == [card(5, C)]
    assert state.turn_index == 1
    # P1 charge aussi, puis P0 charge une deuxième fois : c'est le plafond.
    announce(state, 1, Action.CHARGE)
    announce(state, 0, Action.CHARGE)
    assert len(state.players[0].charges) == 2
    announce(state, 1, Action.CHARGE)
    with pytest.raises(IllegalMove):
        announce(state, 0, Action.CHARGE)
    assert total_cards(state) == 4 + 6


def test_defend_self_replaces_defense_and_discards_old():
    state = two_players([card(12, C)])
    events = announce(state, 0, Action.DEFEND)
    # Annonce à l'aveugle : rien n'est pioché tant que la cible n'est pas désignée.
    assert state.phase is Phase.TARGET and state.draw_pile == [card(12, C)]
    assert events == [{"type": "announced", "player": 0, "action": "defend"}]
    events = choose_target(state, 0, 0)
    assert events[0]["type"] == "revealed" and events[0]["card"] == card(12, C).to_dict()
    assert events[1]["type"] == "defense_changed"
    assert state.players[0].defense == card(12, C)
    assert state.discard == [card(5, S)]
    assert state.phase is Phase.ACTION and state.turn_index == 1


def test_defend_other_can_weaken_them():
    state = two_players([card(2, C)])
    announce(state, 0, Action.DEFEND)
    choose_target(state, 0, 1)
    assert state.players[1].defense == card(2, C)
    assert state.discard == [card(7, D)]


def test_attack_blocked_by_defense_still_discards_cards():
    state = two_players([card(6, C)])  # 6 contre une défense de 7 : rien ne passe
    announce(state, 0, Action.ATTACK)
    events = choose_target(state, 0, 1)
    attacked = events[1]
    assert attacked["type"] == "attacked" and attacked["damage"] == 0
    assert state.players[1].life_total == 17
    assert state.discard == [card(6, C)]
    assert [e["type"] for e in events] == ["revealed", "attacked", "turn"]


def test_attack_with_charges_adds_them_and_consumes_them():
    state = two_players([card(12, D), card(6, S), card(4, C)])
    state.players[0].charges = [card(3, H), card(2, S)]
    announce(state, 0, Action.ATTACK)
    events = choose_target(state, 0, 1)
    attacked = events[1]
    assert attacked["total"] == 9 and attacked["defense"] == 7 and attacked["damage"] == 2
    assert state.players[0].charges == []
    assert state.players[1].life_total == 15
    assert state.players[1].lives == [card(9, C), card(6, S)]
    assert set(state.discard) == {card(4, C), card(3, H), card(2, S), card(8, H)}


def test_hit_defender_loses_his_charges():
    # 10 contre 7 : 3 dégâts, 17 → 14 = 9 + 5.
    state = two_players([card(12, D), card(5, S), card(10, C)])
    state.players[1].charges = [card(2, H)]
    announce(state, 0, Action.ATTACK)
    events = choose_target(state, 0, 1)
    assert {"type": "charges_lost", "player": 1} in events
    assert state.players[1].charges == []
    assert state.players[1].lives == [card(9, C), card(5, S)]
    assert card(2, H) in state.discard


def test_cannot_attack_self_and_state_is_kept():
    state = two_players([card(13, C)])
    announce(state, 0, Action.ATTACK)
    with pytest.raises(InvalidAction):
        choose_target(state, 0, 0)
    assert state.phase is Phase.TARGET and state.draw_pile == [card(13, C)]
    choose_target(state, 0, 1)


def test_hawk_eye_sees_top_card_only_when_single_ace():
    state = playing_state(
        [
            player("P0", [card(1, H)], card(5, S)),
            player("P1", [card(9, C), card(8, H)], card(7, D)),
        ],
        draw=[card(2, C), card(11, D)],
    )
    assert peek(state, 0) == card(11, D)
    assert peek(state, 1) is None
    state.players[0].lives = [card(1, H), card(1, S)]
    assert peek(state, 0) is None
