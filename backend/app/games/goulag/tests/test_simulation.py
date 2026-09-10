"""Parties complètes jouées au hasard : terminaison et conservation des 52 cartes."""

import random

import pytest

from app.games.goulag.engine import (
    Action,
    GameStatus,
    Phase,
    Suit,
    add_player,
    announce,
    can_charge,
    choose_suit,
    choose_target,
    create_game,
    set_ready,
)
from app.games.goulag.tests.helpers import total_cards

MAX_STEPS = 5000


def run_random_game(seed: int, num_players: int) -> None:
    rng = random.Random(seed)
    state = create_game("P0", seed=seed)
    for i in range(1, num_players):
        add_player(state, f"P{i}")
    for i in range(num_players):
        set_ready(state, i)
    assert state.status is GameStatus.PLAYING
    assert total_cards(state) == 52

    for _ in range(MAX_STEPS):
        if state.status is GameStatus.FINISHED:
            break
        if state.phase is Phase.REVIVAL:
            choose_suit(state, state.reviving, rng.choice(list(Suit)))
        elif state.phase is Phase.TARGET:
            me = state.turn_index
            if state.pending_action is Action.DEFEND:
                target = rng.choice(state.alive_indices())
            else:
                target = rng.choice([i for i in state.alive_indices() if i != me])
            choose_target(state, me, target)
        else:
            me = state.turn_index
            options = [Action.ATTACK, Action.DEFEND] + (
                [Action.CHARGE] if can_charge(state, me) else []
            )
            announce(state, me, rng.choice(options))
        assert total_cards(state) == 52, "les 52 cartes doivent toujours être quelque part"
        for p in state.players:
            if p.alive and state.phase is not Phase.REVIVAL:
                assert p.life_total > 0 and p.defense is not None
            if not p.alive and p.finish_rank != 1:
                assert p.card_count == 0, "un éliminé ne garde aucune carte"

    assert state.status is GameStatus.FINISHED, f"partie non terminée (seed={seed})"
    ranks = sorted(p.finish_rank for p in state.players)
    assert ranks == list(range(1, num_players + 1))


@pytest.mark.parametrize("seed", range(40))
def test_random_games_terminate_cleanly(seed):
    run_random_game(seed, num_players=2 + seed % 5)
