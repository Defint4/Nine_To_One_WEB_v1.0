"""Entraînement PPO self-play du bot Nine to One (2 joueurs).

- Self-play symétrique (le même réseau joue les deux sièges), ancré par des
  parties contre les heuristiques (économe, hasard) pour rester calibré.
- Retours Monte-Carlo (gamma=1) : avantage = résultat final - valeur estimée.
- Éval périodique en glouton contre hasard / économe / monte-carlo.
"""

import argparse
import random
import sys
import time

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, "/home/defint/projects/nine_to_one/ml")

from rl_env import Game, N_ACTIONS, OBS_DIM, decode_action  # noqa: E402
from strategies import MonteCarlo, Rand, SaveSpecials  # noqa: E402

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class Net(nn.Module):
    def __init__(self, hidden=256):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(OBS_DIM, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU()
        )
        self.pi = nn.Linear(hidden, N_ACTIONS)
        self.v = nn.Linear(hidden, 1)

    def forward(self, x, mask):
        h = self.body(x)
        logits = self.pi(h)
        logits = logits.masked_fill(~mask, -1e9)
        return logits, self.v(h).squeeze(-1)


def heuristic_move(game, policy, rng):
    """Fait jouer une heuristique de strategies.py sur l'état du jeu."""
    state = game.state
    seat = state.turn_index
    v, count, d = policy.choose(state, seat, None, rng)
    game.step_raw(v, count, d)


def advance_heuristics(game, opp_seat, opp_policy, rng):
    while not game.done and game.state.turn_index == opp_seat:
        heuristic_move(game, opp_policy, rng)


class EnvSlot:
    def __init__(self, seed, rng):
        self.game = Game(seed)
        r = rng.random()
        if r < 0.70:
            self.opp_policy = None  # self-play
            self.opp_seat = -1
        else:
            self.opp_policy = SaveSpecials() if r < 0.92 else Rand()
            self.opp_seat = rng.randrange(2)
        self.rng = random.Random(seed ^ 0x5EED)
        advance_heuristics(self.game, self.opp_seat, self.opp_policy, self.rng) if self.opp_policy else None


def collect(net, n_envs, seed0, rng):
    """Joue n_envs parties jusqu'au bout ; renvoie les transitions du réseau."""
    slots = [EnvSlot(seed0 + i, rng) for i in range(n_envs)]
    # streams[(env, seat)] = listes de (obs, mask, action, logp, value)
    streams = {}
    obs_l, mask_l, act_l, logp_l, val_l, ret_l = [], [], [], [], [], []
    active = [s for s in slots if not s.game.done]
    with torch.no_grad():
        while active:
            batch_obs, batch_mask, metas = [], [], []
            for slot in active:
                o, m, seat = slot.game.obs_mask()
                batch_obs.append(o)
                batch_mask.append(m)
                metas.append((slot, seat))
            x = torch.as_tensor(np.stack(batch_obs), device=DEVICE)
            mk = torch.as_tensor(np.stack(batch_mask), device=DEVICE)
            logits, values = net(x, mk)
            dist = torch.distributions.Categorical(logits=logits)
            actions = dist.sample()
            logps = dist.log_prob(actions)
            for k, (slot, seat) in enumerate(metas):
                a = int(actions[k])
                streams.setdefault((id(slot), seat), []).append(
                    (batch_obs[k], batch_mask[k], a, float(logps[k]), float(values[k]))
                )
                slot.game.step(a)
                if slot.opp_policy and not slot.game.done:
                    advance_heuristics(slot.game, slot.opp_seat, slot.opp_policy, slot.rng)
            done_now = [s for s in active if s.game.done]
            for slot in done_now:
                for seat in (0, 1):
                    key = (id(slot), seat)
                    if key not in streams:
                        continue
                    r = slot.game.result(seat)
                    for obs, mask, a, lp, v in streams.pop(key):
                        obs_l.append(obs)
                        mask_l.append(mask)
                        act_l.append(a)
                        logp_l.append(lp)
                        val_l.append(v)
                        ret_l.append(r)
            active = [s for s in active if not s.game.done]
    return (
        np.stack(obs_l),
        np.stack(mask_l),
        np.array(act_l),
        np.array(logp_l, dtype=np.float32),
        np.array(val_l, dtype=np.float32),
        np.array(ret_l, dtype=np.float32),
    )


def ppo_update(net, opt, batch, epochs=4, clip=0.2, ent_coef=0.01, vf_coef=0.5, bs=4096):
    obs, mask, act, logp_old, val_old, ret = batch
    adv = ret - val_old
    adv = (adv - adv.mean()) / (adv.std() + 1e-6)
    n = len(obs)
    obs_t = torch.as_tensor(obs, device=DEVICE)
    mask_t = torch.as_tensor(mask, device=DEVICE)
    act_t = torch.as_tensor(act, device=DEVICE)
    logp_t = torch.as_tensor(logp_old, device=DEVICE)
    adv_t = torch.as_tensor(adv, device=DEVICE)
    ret_t = torch.as_tensor(ret, device=DEVICE)
    for _ in range(epochs):
        idx = torch.randperm(n, device=DEVICE)
        for s in range(0, n, bs):
            b = idx[s : s + bs]
            logits, values = net(obs_t[b], mask_t[b])
            dist = torch.distributions.Categorical(logits=logits)
            logp = dist.log_prob(act_t[b])
            ratio = torch.exp(logp - logp_t[b])
            l1 = ratio * adv_t[b]
            l2 = torch.clamp(ratio, 1 - clip, 1 + clip) * adv_t[b]
            pi_loss = -torch.min(l1, l2).mean()
            v_loss = ((values - ret_t[b]) ** 2).mean()
            ent = dist.entropy().mean()
            loss = pi_loss + vf_coef * v_loss - ent_coef * ent
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()


# ---------------------------------------------------------------------------
# Évaluation en glouton contre les heuristiques
# ---------------------------------------------------------------------------


def net_move(net, game):
    o, m, _seat = game.obs_mask()
    with torch.no_grad():
        logits, _ = net(
            torch.as_tensor(o, device=DEVICE).unsqueeze(0),
            torch.as_tensor(m, device=DEVICE).unsqueeze(0),
        )
        a = int(torch.argmax(logits, dim=-1))
    game.step(a)


def eval_vs(net, opponent, games, seed0):
    wins = draws = 0
    rng = random.Random(seed0)
    for g in range(games):
        game = Game(seed0 + g * 7919)
        net_seat = g % 2
        while not game.done:
            if game.state.turn_index == net_seat:
                net_move(net, game)
            else:
                heuristic_move(game, opponent, rng)
        r = game.result(net_seat)
        if r > 0:
            wins += 1
        elif r == 0:
            draws += 1
    decided = games - draws
    return wins / decided if decided else 0.5, draws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--envs", type=int, default=96)
    ap.add_argument("--eval-every", type=int, default=8)
    ap.add_argument("--out", default="bot_policy.pt")
    args = ap.parse_args()

    torch.manual_seed(0)
    rng = random.Random(0)
    net = Net().to(DEVICE)
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)
    print(f"device={DEVICE} obs={OBS_DIM} actions={N_ACTIONS}", flush=True)

    start = time.monotonic()  # insensible aux sauts d'horloge WSL
    it = 0
    best = -1.0
    while time.monotonic() - start < args.minutes * 60:
        it += 1
        batch = collect(net, args.envs, seed0=it * 100_000, rng=rng)
        ppo_update(net, opt, batch)
        torch.save({"model": net.state_dict(), "obs_dim": OBS_DIM}, args.out + ".last")
        print(f"iter {it} n={len(batch[0])} t={(time.monotonic() - start) / 60:.1f}min", flush=True)
        if it % args.eval_every == 0:
            net.eval()
            wr_r, _ = eval_vs(net, Rand(), 200, seed0=it)
            wr_e, _ = eval_vs(net, SaveSpecials(), 200, seed0=it + 1)
            wr_m, _ = eval_vs(net, MonteCarlo(rollouts=12), 30, seed0=it + 2)
            net.train()
            el = (time.monotonic() - start) / 60
            print(
                f"EVAL it={it} t={el:5.1f}min n={len(batch[0])} "
                f"vs_hasard={wr_r:6.1%} vs_econome={wr_e:6.1%} vs_mc={wr_m:6.1%}",
                flush=True,
            )
            score = wr_e + wr_r
            if score > best:
                best = score
                torch.save({"model": net.state_dict(), "obs_dim": OBS_DIM}, args.out)
                print(f"SAVE  it={it} score={score:.3f}", flush=True)
    print("FIN entraînement", flush=True)


if __name__ == "__main__":
    main()
