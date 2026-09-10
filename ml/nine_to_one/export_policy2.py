"""Exporte l'acteur v2 (.best.pt) en .npz numpy et vérifie la parité avec torch.

Usage : rlenv/bin/python export_policy2.py v2.best.pt ../../backend/app/games/nine_to_one/bot_policy_v2.npz
"""

import random
import sys

import numpy as np
import torch
from pathlib import Path

# Chemins relatifs au repo : ce dossier (ml/nine_to_one) et le backend.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"

sys.path.insert(0, str(HERE))

from rl_env2 import Game  # noqa: E402
from train_v2 import build_torch, np_logits  # noqa: E402


def critic_numpy(critic):
    sd = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in critic.state_dict().items()}
    return {
        "w1": sd["net.0.weight"], "b1": sd["net.0.bias"], "g1": sd["net.1.weight"], "be1": sd["net.1.bias"],
        "w2": sd["net.3.weight"], "b2": sd["net.3.bias"], "g2": sd["net.4.weight"], "be2": sd["net.4.bias"],
        "w3": sd["net.6.weight"], "b3": sd["net.6.bias"], "wv": sd["net.8.weight"], "bv": sd["net.8.bias"],
    }


def main(pt_path, npz_path, games=30):
    _, _, Actor, Critic = build_torch()
    ck = torch.load(pt_path, map_location="cpu")
    actor, critic = Actor(), Critic()
    actor.load_state_dict(ck["actor"])
    critic.load_state_dict(ck["critic"])
    actor.eval()
    w = actor.numpy_weights()
    np.savez(npz_path, **w)
    critic_path = npz_path.replace(".npz", "_critic.npz")
    np.savez(critic_path, **critic_numpy(critic))
    print("critique exporté :", critic_path)
    rng = random.Random(0)
    checked = agree = 0
    max_diff = 0.0
    for g in range(games):
        game = Game(g * 13 + 5)
        while not game.done:
            obs, mask, _ = game.obs_mask()
            with torch.no_grad():
                lt = actor(torch.as_tensor(obs)[None], torch.as_tensor(mask)[None])[0].numpy()
            ln = np.where(mask, np_logits(w, obs[None])[0], -1e9)
            max_diff = max(max_diff, float(np.abs(lt[mask] - ln[mask]).max()))
            agree += int(np.argmax(lt) == np.argmax(ln))
            checked += 1
            legal = np.flatnonzero(mask)
            game.step(int(rng.choice(legal)) if rng.random() < 0.3 else int(np.argmax(ln)))
    print(f"exporté {npz_path} (it={ck.get('it')}) ; parité argmax {agree}/{checked}, écart max {max_diff:.2e}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
