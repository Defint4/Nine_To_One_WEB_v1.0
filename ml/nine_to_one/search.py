"""Politique « recherche » côté ML : adaptateur vers le cerveau de production.

La recherche elle-même (déterminisation des cartes cachées, bandit PUCT guidé
par le réseau, évaluation des feuilles par le critique) vit dans
backend/app/games/nine_to_one/botbrain.py : c'est exactement ce que joue le serveur. Ici on se
contente de charger d'autres poids et de la brancher sur une partie rl_env2,
pour l'évaluer hors ligne (ml/ladder.py) sans risque de divergence.
"""

import random
import sys
import time
from pathlib import Path

# Chemins relatifs au repo : ce dossier (ml/nine_to_one) et le backend.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BACKEND))

from app.games.nine_to_one.botbrain import STUCK, Brain, search_action  # noqa: E402,F401
from rl_env2 import Game  # noqa: E402


class Searcher:
    """Joue par recherche ; `game` est une partie rl_env2 (sa mémoire suffit)."""

    name = "v2-recherche"

    def __init__(self, actor_npz, critic_npz, n_sims=220, horizon=30, time_budget=0.8, seed=0):
        Brain.load(actor_npz, critic_npz)
        self.w, self.wc = Brain.actor(), Brain.critic()
        self.n_sims, self.horizon, self.time_budget = n_sims, horizon, time_budget
        self.rng = random.Random(seed)

    def attach(self, game):
        Brain._actor, Brain._critic = self.w, self.wc  # plusieurs politiques en lice

    def act(self, game):
        a = search_action(
            game.state, game.mem, game.seat, self.rng, self.n_sims, self.horizon, self.time_budget
        )
        game.step(a)


if __name__ == "__main__":
    # Bench : recherche vs réseau glouton, et temps par décision.
    from train_v2 import greedy_act

    actor_npz, critic_npz = sys.argv[1], sys.argv[2]
    games = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    budget = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
    s = Searcher(actor_npz, critic_npz, time_budget=budget)
    wins = draws = 0
    t_search, n_search = 0.0, 0
    for g in range(games):
        game = Game(9000 + g, n_players=2)
        me = g % 2
        s.attach(game)
        while not game.done:
            if game.seat == me:
                t0 = time.monotonic()
                s.act(game)
                t_search += time.monotonic() - t0
                n_search += 1
            else:
                greedy_act(s.w, game)
        r = game.result(me)
        wins += r > 0
        draws += r == 0
        print(f"  partie {g}: {r:+.0f}", flush=True)
    print(
        f"recherche vs glouton : {wins}/{games} victoires ({draws} nulles) ; "
        f"{t_search / max(n_search, 1) * 1000:.0f} ms par décision ; donnes écartées : {STUCK[0]}"
    )
