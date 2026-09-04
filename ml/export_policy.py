"""Exporte le checkpoint PPO (.pt) en poids numpy (.npz) et vérifie que
l'inférence numpy pure (celle du backend, sans torch) reproduit l'argmax torch.

Usage : rlenv/bin/python export_policy.py bot_policy.pt ../backend/app/bot_policy.npz
"""

import random
import sys

import numpy as np
import torch

sys.path.insert(0, "/home/defint/projects/nine_to_one/ml")

from rl_env import Game  # noqa: E402
from train_ppo import Net  # noqa: E402


def export(pt_path: str, npz_path: str) -> dict:
    ckpt = torch.load(pt_path, map_location="cpu")
    net = Net()
    net.load_state_dict(ckpt["model"])
    net.eval()
    sd = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in net.state_dict().items()}
    weights = {
        "w1": sd["body.0.weight"],
        "b1": sd["body.0.bias"],
        "w2": sd["body.2.weight"],
        "b2": sd["body.2.bias"],
        "wpi": sd["pi.weight"],
        "bpi": sd["pi.bias"],
        "wv": sd["v.weight"],
        "bv": sd["v.bias"],
    }
    np.savez(npz_path, **weights)
    return weights


def forward_np(w: dict, obs: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Même calcul que app/bots.py : MLP 91→256→256→52, masque à -1e9."""
    h = np.maximum(w["w1"] @ obs + w["b1"], 0.0)
    h = np.maximum(w["w2"] @ h + w["b2"], 0.0)
    logits = w["wpi"] @ h + w["bpi"]
    return np.where(mask, logits, -1e9)


def verify(pt_path: str, w: dict, games: int = 40) -> None:
    ckpt = torch.load(pt_path, map_location="cpu")
    net = Net()
    net.load_state_dict(ckpt["model"])
    net.eval()
    rng = random.Random(0)
    checked = agree = 0
    max_diff = 0.0
    for g in range(games):
        game = Game(g * 31 + 7)
        while not game.done:
            obs, mask, _ = game.obs_mask()
            with torch.no_grad():
                lt, _ = net(torch.as_tensor(obs).unsqueeze(0), torch.as_tensor(mask).unsqueeze(0))
            lt = lt[0].numpy()
            ln = forward_np(w, obs, mask)
            max_diff = max(max_diff, float(np.abs(lt[mask] - ln[mask]).max()))
            checked += 1
            agree += int(np.argmax(lt) == np.argmax(ln))
            legal = np.flatnonzero(mask)
            game.step(int(rng.choice(legal)) if rng.random() < 0.3 else int(np.argmax(ln)))
    print(f"vérif numpy vs torch : {agree}/{checked} argmax identiques, écart max logits={max_diff:.2e}")


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    w = export(src, dst)
    print("exporté :", dst, {k: v.shape for k, v in w.items()})
    verify(src, w)
