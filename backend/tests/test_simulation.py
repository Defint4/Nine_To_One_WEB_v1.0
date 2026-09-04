"""Parties complètes jouées aléatoirement : terminaison et conservation des 52 cartes."""

import random

import pytest

from app.engine import (
    Comparator,
    GameStatus,
    add_player,
    create_game,
    flip_face_down,
    play_cards,
    playable_values,
    set_ready,
)

MAX_STEPS = 5000


def total_cards(state):
    in_zones = sum(p.card_count for p in state.players)
    return in_zones + len(state.draw_pile) + len(state.pile) + len(state.discard)


def run_random_game(seed: int, num_players: int) -> None:
    rng = random.Random(seed)
    state = create_game("P0", seed=seed)
    for i in range(1, num_players):
        add_player(state, f"P{i}")
    for i in range(num_players):
        set_ready(state, i)
    assert state.status is GameStatus.PLAYING

    for _ in range(MAX_STEPS):
        if state.status is GameStatus.FINISHED:
            break
        idx = state.turn_index
        player = state.players[idx]
        if not player.hand:
            flip_face_down(state, idx, rng.randrange(len(player.face_down)))
        else:
            values = playable_values(state, idx)
            assert values, "le joueur au trait doit toujours avoir un coup ou avoir ramassé"
            value = rng.choice(sorted(values))
            copies = sum(1 for c in player.hand if c.value == value)
            count = rng.randint(1, copies)
            direction = rng.choice([Comparator.GTE, Comparator.LTE]) if value == 7 else None
            play_cards(state, idx, value, count=count, direction=direction)
        assert total_cards(state) == 52, "les 52 cartes doivent toujours être quelque part"

    assert state.status is GameStatus.FINISHED, f"partie non terminée (seed={seed})"
    ranks = sorted(p.finish_rank for p in state.players)
    assert ranks == list(range(1, num_players + 1))


@pytest.mark.parametrize("seed", range(20))
def test_random_games_terminate_cleanly(seed):
    run_random_game(seed, num_players=2 + seed % 4)
