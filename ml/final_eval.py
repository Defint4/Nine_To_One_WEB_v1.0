"""Évaluation finale robuste d'un checkpoint : glouton contre les heuristiques.

Usage : rlenv/bin/python final_eval.py bot_policy.pt [--rand 1000 --eco 1000 --mc 200]
"""

import argparse
import sys
import time

import torch

sys.path.insert(0, "/home/defint/projects/nine_to_one/ml")

from strategies import MonteCarlo, Rand, SaveSpecials  # noqa: E402
from train_ppo import DEVICE, Net, eval_vs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("--rand", type=int, default=1000)
    ap.add_argument("--eco", type=int, default=1000)
    ap.add_argument("--mc", type=int, default=200)
    ap.add_argument("--rollouts", type=int, default=20)
    args = ap.parse_args()

    ckpt = torch.load(args.checkpoint, map_location=DEVICE)
    net = Net().to(DEVICE)  # eval_vs place ses tenseurs sur DEVICE
    net.load_state_dict(ckpt["model"])
    net.eval()
    for label, opp, games in (
        ("hasard", Rand(), args.rand),
        ("econome", SaveSpecials(), args.eco),
        (f"monte-carlo({args.rollouts})", MonteCarlo(rollouts=args.rollouts), args.mc),
    ):
        t0 = time.monotonic()
        rate, draws = eval_vs(net, opp, games, seed0=424242)
        print(
            f"vs {label:18s} {games:5d} parties  victoires={rate:6.1%}  nuls={draws:3d}"
            f"  ({time.monotonic() - t0:.0f}s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
