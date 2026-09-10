"""Parité v2 : app.botbrain (instantané depuis la vue + mémoire) == rl_env2.Game.obs_mask.

Usage (depuis backend/, pour le .env) : .venv/bin/python ../ml/nine_to_one/check_obs_parity2.py
"""

import random
import sys
import uuid

import numpy as np
from pathlib import Path

# Chemins relatifs au repo : ce dossier (ml/nine_to_one) et le backend.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BACKEND))

from app.games.nine_to_one.botbrain import Memory, obs_mask, snapshot_from_state, snapshot_from_view  # noqa: E402
from app.games.nine_to_one.spec import NineToOne, RoomData  # noqa: E402
from app.rooms.manager import Room, Seat  # noqa: E402
from app.rooms.views import room_view  # noqa: E402
from rl_env2 import Game  # noqa: E402


def main(games=300):
    rng = random.Random(0)
    checked = 0
    for g in range(games):
        game = Game(g)
        room = Room(code="0000", spec=NineToOne(), state=game.state, data=RoomData())
        room.seats = [Seat(player_id=uuid.uuid4(), pseudo=p.name, avatar="chat-0") for p in game.state.players]
        mem = Memory(game.n)
        orig = game._apply

        def apply(events, _orig=orig, _mem=mem, _room=room):
            _orig(events)
            _mem.on_events(events, np.array([0] * 13, dtype=np.float32) + game.mem.pile)

        game._apply = apply
        while not game.done:
            obs_ref, mask_ref, seat = game.obs_mask()
            for snap in (snapshot_from_view(room_view(room, seat)), snapshot_from_state(game.state, seat)):
                obs, mask = obs_mask(snap, mem)
                assert np.array_equal(mask, mask_ref), (g, seat)
                assert np.allclose(obs, obs_ref, atol=1e-6), (g, seat, np.flatnonzero(~np.isclose(obs, obs_ref)))
            assert np.array_equal(mem.known, game.mem.known) and np.array_equal(mem.discard, game.mem.discard)
            checked += 1
            game.step(int(rng.choice(np.flatnonzero(mask_ref))))
    print(f"parité v2 OK sur {checked} décisions ({games} parties, 2 à 5 joueurs)")


if __name__ == "__main__":
    main()
