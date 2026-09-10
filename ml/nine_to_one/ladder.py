"""Échelle Elo : classe des politiques sur des duels à 2 joueurs et des tables à 4.

Participants : hasard, économe, monte-carlo (20 rollouts), réseau v1, acteur v2
glouton, v2 + recherche (Expert), et d'éventuels checkpoints de ligue.

Usage : rlenv/bin/python ladder.py v2.npz v2_critic.npz [--games 200] [--fast]
"""

import argparse
import itertools
import random
import sys
import time

import numpy as np
from pathlib import Path

# Chemins relatifs au repo : ce dossier (ml/nine_to_one) et le backend.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"

sys.path.insert(0, str(HERE))

from rl_env2 import Game  # noqa: E402
from search import Searcher  # noqa: E402
from strategies import MonteCarlo, Rand, SaveSpecials  # noqa: E402
from train_v2 import V1Adapter, greedy_act, heuristic_step  # noqa: E402


class Heuristic:
    def __init__(self, name, policy):
        self.name, self.policy, self.rng = name, policy, random.Random(0)

    def attach(self, game):
        pass

    def act(self, game):
        heuristic_step(game, self.policy, self.rng)


class Greedy:
    def __init__(self, name, npz):
        self.name = name
        with np.load(npz) as f:
            self.w = {k: f[k] for k in f.files}

    def attach(self, game):
        pass  # poids portés par l'instance, rien à réarmer

    def act(self, game):
        greedy_act(self.w, game)


class V1:
    name = "v1"

    def __init__(self, npz):
        self.adapter = V1Adapter(npz)

    def attach(self, game):
        self.adapter.attach(game)

    def act(self, game):
        self.adapter.act(game)


class Expert:
    name = "v2-recherche"

    def __init__(self, actor, critic, n_sims, horizon, time_budget):
        self.s = Searcher(actor, critic, n_sims=n_sims, horizon=horizon, time_budget=time_budget)

    def attach(self, game):
        self.s.attach(game)

    def act(self, game):
        self.s.act(game)


def duel(a, b, games, seed0):
    """Score de a contre b (0..1), sièges alternés."""
    pts = 0.0
    for g in range(games):
        game = Game(seed0 + g * 101, n_players=2)
        seat_a = g % 2
        a.attach(game)
        b.attach(game)
        while not game.done:
            (a if game.seat == seat_a else b).act(game)
        r = game.result(seat_a)
        pts += 1.0 if r > 0 else 0.5 if r == 0 else 0.0
    return pts / games


def elo_from_scores(names, scores, iters=2000, lr=8.0):
    """Ratings par descente sur la log-vraisemblance des scores observés (ancre : hasard = 1000)."""
    n = len(names)
    r = np.zeros(n)
    for _ in range(iters):
        grad = np.zeros(n)
        for (i, j), s in scores.items():
            e = 1.0 / (1.0 + 10 ** ((r[j] - r[i]) / 400))
            grad[i] += s - e
            grad[j] -= s - e
        r += lr * grad
    return {names[i]: 1000 + r[i] - r[names.index("hasard")] for i in range(n)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("actor")
    ap.add_argument("critic")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--v1", default=str(HERE / "bot_policy_v1.npz"))
    ap.add_argument("--n-sims", type=int, default=220)
    ap.add_argument("--budget", type=float, default=0.8)
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--fast", action="store_true", help="sans Expert ni Monte-Carlo (lents)")
    args = ap.parse_args()

    players = [
        Heuristic("hasard", Rand()),
        Heuristic("econome", SaveSpecials()),
        V1(args.v1),
        Greedy("v2-glouton", args.actor),
    ]
    if not args.fast:
        players.append(Heuristic("monte-carlo-20", MonteCarlo(rollouts=20)))
        players.append(Expert(args.actor, args.critic, args.n_sims, args.horizon, args.budget))
    names = [p.name for p in players]
    scores = {}
    for i, j in itertools.combinations(range(len(players)), 2):
        slow = any(p.name in ("monte-carlo-20", "v2-recherche") for p in (players[i], players[j]))
        games = max(40, args.games // 4) if slow else args.games
        t0 = time.monotonic()
        s = duel(players[i], players[j], games, seed0=1234 + i * 17 + j)
        scores[(i, j)] = s
        print(f"{names[i]:>16s} vs {names[j]:<16s} {s:6.1%}  ({games} parties, {time.monotonic() - t0:.0f}s)", flush=True)
    elo = elo_from_scores(names, scores)
    print("\nElo (hasard = 1000) :")
    for name, e in sorted(elo.items(), key=lambda kv: -kv[1]):
        print(f"  {name:>16s} {e:7.0f}")


if __name__ == "__main__":
    main()
