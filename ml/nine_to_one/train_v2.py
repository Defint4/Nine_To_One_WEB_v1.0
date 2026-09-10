"""Entraînement v2 du bot Nine to One : PPO self-play en ligue, 2 à 5 joueurs.

Ingrédients :
- Acteur (politique) sur l'observation honnête ; critique séparé qui voit en
  plus les cartes cachées (mains adverses, cachées, pioche) : « critique
  centralisé », variance bien plus faible en information imparfaite. Seul
  l'acteur est exporté.
- Collecte dans des workers CPU (inférence numpy, comme en production), PPO sur
  GPU dans le processus principal. GAE(λ) avec γ=1 (récompense terminale par rang).
- Ligue d'adversaires : checkpoints passés + heuristiques ; adversaires tirés
  par PFSP (priorité à ceux que la politique courante bat le moins), pour éviter
  les cycles du self-play pur et rester robuste à tous les styles.
- Éval périodique en glouton : hasard, économe, réseau v1, tables à 4.

Usage : rlenv/bin/python train_v2.py --minutes 300 --workers 6 --envs 40 --out v2
"""

import argparse
import multiprocessing as mp
import os
import random
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

# Un thread BLAS par processus : les matrices sont petites, et 6 workers ×
# 6 threads se marchent dessus (collecte 15× plus lente sinon).
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402

# Chemins relatifs au repo : ce dossier (ml/nine_to_one) et le backend.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"

ML = str(HERE)
sys.path.insert(0, ML)

from rl_env2 import N_ACTIONS, OBS_DIM, PRIV_DIM, Game, counts13  # noqa: E402

HIDDEN = (512, 512, 256)
LN_EPS = 1e-5


# ---------------------------------------------------------------------------
# Inférence numpy (identique à celle du backend)
# ---------------------------------------------------------------------------


def np_layernorm(h, g, b):
    mu = h.mean(-1, keepdims=True)
    var = ((h - mu) ** 2).mean(-1, keepdims=True)
    return (h - mu) / np.sqrt(var + LN_EPS) * g + b


def np_logits(w, x):
    """x : [B, OBS_DIM] → logits [B, 52] (avant masque)."""
    h = np.maximum(np_layernorm(x @ w["w1"].T + w["b1"], w["g1"], w["be1"]), 0.0)
    h = np.maximum(np_layernorm(h @ w["w2"].T + w["b2"], w["g2"], w["be2"]), 0.0)
    h = np.maximum(h @ w["w3"].T + w["b3"], 0.0)
    return h @ w["wpi"].T + w["bpi"]


def masked_softmax(logits, mask):
    z = np.where(mask, logits, -1e9)
    z = z - z.max(-1, keepdims=True)
    p = np.exp(z) * mask
    return p / p.sum(-1, keepdims=True)


# ---------------------------------------------------------------------------
# Adversaires heuristiques et réseau v1 (pour l'éval)
# ---------------------------------------------------------------------------


def heuristic_step(game, policy, rng):
    v, count, d = policy.choose(game.state, game.seat, None, rng)
    game.step_raw(v, count, d)


class V1Adapter:
    """Fait jouer le réseau v1 (obs 91 dims, 2 joueurs) dans une partie v2, avec
    exactement sa mémoire d'entraînement (rl_env v1) reconstruite depuis les
    mêmes événements."""

    def __init__(self, npz_path):
        with np.load(npz_path) as f:
            self.w = {k: f[k] for k in f.files}

    def attach(self, game):
        self.known = [np.zeros(13, dtype=np.float32) for _ in range(2)]
        self.seen_gone = np.zeros(13, dtype=np.float32)
        orig = game._apply

        def apply(events, _orig=orig):
            pile_before = game.mem.pile.copy()
            _orig(events)
            for e in events:
                t = e["type"]
                if t == "cards_played":
                    for cd in e["cards"]:
                        i = cd["value"] - 2
                        if self.known[e["player"]][i] > 0:
                            self.known[e["player"]][i] -= 1
                elif t == "pile_picked_up":
                    self.known[e["player"]] += pile_before
                elif t == "card_flipped":
                    self.known[e["player"]][e["card"]["value"] - 2] += 1
                elif t == "pile_cut":
                    self.seen_gone += pile_before
                    for pe in events:
                        if pe["type"] == "cards_played":
                            for cd in pe["cards"]:
                                self.seen_gone[cd["value"] - 2] += 1

        game._apply = apply

    def act(self, game):
        from app.games.nine_to_one.engine.state import Comparator

        state = game.state
        seat = state.turn_index
        me, opp = state.players[seat], state.players[1 - seat]
        top = state.pile[-1] if state.pile else None
        top_onehot = np.zeros(14, dtype=np.float32)
        top_onehot[(top.value - 2) if top else 13] = 1.0
        run = 0
        if top:
            run = 1
            for c in reversed(state.pile[:-1]):
                if c.value == top.value:
                    run += 1
                else:
                    break
        cons = state.constraint
        scalars = np.array(
            [
                len(me.hand) / 10.0, len(me.face_up) / 3.0, len(me.face_down) / 3.0,
                len(opp.hand) / 10.0, len(opp.face_down) / 3.0, len(state.pile) / 15.0,
                len(state.draw_pile) / 34.0, run / 4.0,
                1.0 if cons and cons.comparator is Comparator.GTE else 0.0,
                1.0 if cons and cons.comparator is Comparator.LTE and cons.value == 7 else 0.0,
                1.0 if cons and cons.comparator is Comparator.LTE and cons.value == 9 else 0.0,
                1.0 if len(state.draw_pile) == 0 else 0.0,
            ],
            dtype=np.float32,
        )
        obs = np.concatenate(
            [counts13(me.hand), counts13(me.face_up), counts13(opp.face_up),
             self.known[1 - seat], self.seen_gone / 4.0, top_onehot, scalars]
        )
        _, mask, _ = game.obs_mask()
        w = self.w
        h = np.maximum(w["w1"] @ obs + w["b1"], 0.0)
        h = np.maximum(w["w2"] @ h + w["b2"], 0.0)
        logits = w["wpi"] @ h + w["bpi"]
        game.step(int(np.argmax(np.where(mask, logits, -1e9))))


# ---------------------------------------------------------------------------
# Worker de collecte
# ---------------------------------------------------------------------------


class Slot:
    def __init__(self, seed, policies, n_players):
        self.game = Game(seed, n_players=n_players)
        self.policies = policies  # par siège : "learner" | ("league", id) | "eco" | "rand"
        self.streams = defaultdict(list)  # siège apprenant -> transitions


def worker_main(conn, wid, seed):
    from strategies import Rand, SaveSpecials

    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    heur = {"eco": SaveSpecials(), "rand": Rand()}
    league = {}
    while True:
        msg = conn.recv()
        cmd = msg["cmd"]
        if cmd == "stop":
            return
        if cmd == "league_add":
            league[msg["id"]] = msg["weights"]
            continue
        if cmd == "league_drop":
            league.pop(msg["id"], None)
            continue
        actor = msg["actor"]
        mix = msg["mix"]  # {"self": p, "league": {id: w}, "eco": p, "rand": p}
        try:
            episodes, stats = collect(
                actor, league, heur, mix, msg["n_envs"], msg["seed0"], msg["ent_temp"], rng, nprng
            )
        except Exception:  # noqa: BLE001 - un worker ne doit jamais tuer l'entraînement
            traceback.print_exc()
            episodes, stats = [], {}
        conn.send((episodes, stats))


def sample_policies(mix, n, rng):
    if rng.random() < mix["self"] or not (mix["league"] or mix["eco"] > 0):
        return ["learner"] * n
    learner_seat = rng.randrange(n)
    pols = []
    ids = list(mix["league"].keys())
    weights = [mix["league"][i] for i in ids]
    for s in range(n):
        if s == learner_seat:
            pols.append("learner")
            continue
        r = rng.random()
        if r < mix["eco"]:
            pols.append("eco")
        elif r < mix["eco"] + mix["rand"]:
            pols.append("rand")
        elif ids:
            pols.append(("league", rng.choices(ids, weights)[0]))
        else:
            pols.append("learner")
    return pols


STUCK_DUMPS = [0]


def dump_stuck(game):
    """Sauvegarde un état sans coup légal (au plus quelques-uns par worker)."""
    STUCK_DUMPS[0] += 1
    if STUCK_DUMPS[0] > 3:
        return
    import json

    path = f"/tmp/claude-1000/stuck_{os.getpid()}_{STUCK_DUMPS[0]}.json"
    try:
        with open(path, "w") as f:
            json.dump({"state": game.state.to_dict(), "seat": game.state.turn_index}, f)
        print(f"ETAT BLOQUE écrit dans {path}", flush=True)
    except OSError:
        pass


def collect(actor, league, heur, mix, n_envs, seed0, ent_temp, rng, nprng):
    slots = []
    for i in range(n_envs):
        n = rng.choice([2, 2, 2, 3, 3, 4, 5])
        slots.append(Slot(seed0 + i, sample_policies(mix, n, rng), n))
    episodes = []
    stats = defaultdict(lambda: [0.0, 0])  # clé adversaire -> [somme récompense apprenant, n]

    def advance_heuristics(slot):
        g = slot.game
        while not g.done and slot.policies[g.seat] in ("eco", "rand"):
            heuristic_step(g, heur[slot.policies[g.seat]], rng)

    for slot in slots:
        advance_heuristics(slot)
    active = [s for s in slots if not s.game.done]
    while active:
        groups = defaultdict(list)
        for slot in active:
            seat = slot.game.seat
            pol = slot.policies[seat]
            obs, mask, _ = slot.game.obs_mask()
            if not mask.any():
                # Position sans coup légal : on abandonne la partie plutôt que de
                # tirer une action au hasard (elle serait illégale). Rare ; l'état
                # est écrit sur disque pour diagnostic.
                dump_stuck(slot.game)
                slot.game.steps = slot.game.max_steps  # marque la partie comme finie
                continue
            groups[pol].append((slot, seat, obs, mask))
        for pol, items in groups.items():
            w = actor if pol == "learner" else league[pol[1]]
            x = np.stack([it[2] for it in items])
            m = np.stack([it[3] for it in items])
            logits = np_logits(w, x)
            if pol == "learner":
                logits = logits / ent_temp
            p = masked_softmax(logits, m)
            u = nprng.random(len(items))
            acts = (p.cumsum(-1) > u[:, None]).argmax(-1)
            for k, (slot, seat, obs, mask) in enumerate(items):
                a = int(acts[k])
                if pol == "learner":
                    slot.streams[seat].append(
                        (obs, slot.game.priv(seat), mask, a, float(np.log(p[k, a] + 1e-12)))
                    )
                slot.game.step(a)
                advance_heuristics(slot)
        done_now = [s for s in active if s.game.done]
        for slot in done_now:
            opp_key = "self" if all(p == "learner" for p in slot.policies) else "mixed"
            for seat, stream in slot.streams.items():
                r = slot.game.result(seat)
                episodes.append(
                    (
                        np.stack([t[0] for t in stream]),
                        np.stack([t[1] for t in stream]),
                        np.stack([t[2] for t in stream]),
                        np.array([t[3] for t in stream], dtype=np.int64),
                        np.array([t[4] for t in stream], dtype=np.float32),
                        r,
                    )
                )
                for s2, p2 in enumerate(slot.policies):
                    if p2 == "learner":
                        continue
                    key = p2 if isinstance(p2, str) else f"L{p2[1]}"
                    stats[key][0] += r
                    stats[key][1] += 1
                stats[opp_key][0] += r
                stats[opp_key][1] += 1
        active = [s for s in active if not s.game.done]
    return episodes, dict(stats)


# ---------------------------------------------------------------------------
# Réseaux torch
# ---------------------------------------------------------------------------


def build_torch():
    import torch
    import torch.nn as nn

    class Actor(nn.Module):
        def __init__(self):
            super().__init__()
            self.l1 = nn.Linear(OBS_DIM, HIDDEN[0])
            self.n1 = nn.LayerNorm(HIDDEN[0], eps=LN_EPS)
            self.l2 = nn.Linear(HIDDEN[0], HIDDEN[1])
            self.n2 = nn.LayerNorm(HIDDEN[1], eps=LN_EPS)
            self.l3 = nn.Linear(HIDDEN[1], HIDDEN[2])
            self.pi = nn.Linear(HIDDEN[2], N_ACTIONS)

        def forward(self, x, mask):
            h = torch.relu(self.n1(self.l1(x)))
            h = torch.relu(self.n2(self.l2(h)))
            h = torch.relu(self.l3(h))
            return self.pi(h).masked_fill(~mask, -1e9)

        def numpy_weights(self):
            sd = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in self.state_dict().items()}
            return {
                "w1": sd["l1.weight"], "b1": sd["l1.bias"], "g1": sd["n1.weight"], "be1": sd["n1.bias"],
                "w2": sd["l2.weight"], "b2": sd["l2.bias"], "g2": sd["n2.weight"], "be2": sd["n2.bias"],
                "w3": sd["l3.weight"], "b3": sd["l3.bias"], "wpi": sd["pi.weight"], "bpi": sd["pi.bias"],
            }

    class Critic(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(OBS_DIM + PRIV_DIM, HIDDEN[0]), nn.LayerNorm(HIDDEN[0]), nn.ReLU(),
                nn.Linear(HIDDEN[0], HIDDEN[1]), nn.LayerNorm(HIDDEN[1]), nn.ReLU(),
                nn.Linear(HIDDEN[1], HIDDEN[2]), nn.ReLU(),
                nn.Linear(HIDDEN[2], 1),
            )

        def forward(self, x):
            return self.net(x).squeeze(-1)

    return torch, nn, Actor, Critic


# ---------------------------------------------------------------------------
# Éval gloutonne
# ---------------------------------------------------------------------------


def greedy_act(w, game):
    obs, mask, _ = game.obs_mask()
    logits = np_logits(w, obs[None])[0]
    game.step(int(np.argmax(np.where(mask, logits, -1e9))))


def eval_vs(w, opponent, games, seed0, n_players=2, v1=None):
    """Taux de « victoire » (récompense > 0 ⇒ mieux que la médiane ; à 2 joueurs = gagne)."""
    rng = random.Random(seed0)
    wins = draws = 0
    total = 0.0
    for g in range(games):
        game = Game(seed0 + g * 7919, n_players=n_players)
        my_seat = g % n_players
        if v1 is not None:
            v1.attach(game)
        while not game.done:
            if game.seat == my_seat:
                greedy_act(w, game)
            elif v1 is not None:
                v1.act(game)
            else:
                heuristic_step(game, opponent, rng)
        r = game.result(my_seat)
        total += r
        if r > 0:
            wins += 1
        elif r == 0:
            draws += 1
    decided = games - draws
    return (wins / decided if decided else 0.5), total / games


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--envs", type=int, default=40, help="parties par worker et par itération")
    ap.add_argument("--out", default="v2")
    ap.add_argument("--league-every", type=int, default=25)
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--resume", default=None, help="checkpoint .pt (acteur+critique) à reprendre")
    ap.add_argument("--v1", default=str(HERE / "bot_policy_v1.npz"))
    args = ap.parse_args()

    from strategies import Rand, SaveSpecials

    torch, nn, Actor, Critic = build_torch()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(0)
    actor, critic = Actor().to(device), Critic().to(device)
    params = list(actor.parameters()) + list(critic.parameters())
    opt = torch.optim.Adam(params, lr=3e-4, eps=1e-5)
    it0 = 0
    if args.resume:
        ck = torch.load(args.resume, map_location=device)
        actor.load_state_dict(ck["actor"])
        critic.load_state_dict(ck["critic"])
        it0 = ck.get("it", 0)
        print(f"reprise depuis {args.resume} (it={it0})", flush=True)
    v1 = V1Adapter(args.v1) if os.path.exists(args.v1) else None
    print(f"device={device} obs={OBS_DIM} priv={PRIV_DIM} actions={N_ACTIONS} v1={'oui' if v1 else 'non'}", flush=True)

    ctx = mp.get_context("spawn")
    conns, procs = [], []
    for wid in range(args.workers):
        a, b = ctx.Pipe()
        p = ctx.Process(target=worker_main, args=(b, wid, 1000 + wid), daemon=True)
        p.start()
        conns.append(a)
        procs.append(p)

    os.makedirs(args.out + "_league", exist_ok=True)
    league_ids = []
    league_score = {}  # id -> EMA de (r+1)/2 de l'apprenant contre lui
    if args.resume:
        # Reprise : on recharge les membres de ligue déjà sur disque (les 24 plus récents).
        files = sorted(
            (int(f[:-4]), f) for f in os.listdir(args.out + "_league") if f.endswith(".npz")
        )[-24:]
        for lid, f in files:
            with np.load(os.path.join(args.out + "_league", f)) as z:
                lw = {k: z[k] for k in z.files}
            league_ids.append(lid)
            for c in conns:
                c.send({"cmd": "league_add", "id": lid, "weights": lw})
        print(f"ligue rechargée : {len(league_ids)} membres", flush=True)
    total_minutes = args.minutes
    start = time.monotonic()
    it = it0
    best = -9.0
    gamma, lam, clip = 1.0, 0.95, 0.2

    def send_collect(iteration):
        """Lance la collecte de `iteration` sur tous les workers (avec les poids courants)."""
        w = actor.numpy_weights()
        if league_ids:
            pf = {i: (1.0 - league_score.get(i, 0.5)) ** 2 + 0.05 for i in league_ids}
            for i in league_ids[-3:]:
                pf[i] += 0.15  # les plus récents restent souvent présents
        else:
            pf = {}
        mix = {"self": 0.45, "league": pf, "eco": 0.12, "rand": 0.04}
        for k, c in enumerate(conns):
            c.send({"cmd": "collect", "actor": w, "mix": mix, "n_envs": args.envs,
                    "seed0": iteration * 1_000_000 + k * 10_000, "ent_temp": 1.0})
        return w, time.monotonic()

    # Collecte asynchrone : pendant que le GPU apprend sur l'itération N, les
    # workers jouent déjà N+1 avec les poids d'avant la mise à jour (retard d'une
    # itération, que le ratio tronqué de PPO absorbe sans peine).
    w, t_sent = send_collect(it0 + 1)
    try:
        while time.monotonic() - start < total_minutes * 60:
            it += 1
            frac = min(1.0, (time.monotonic() - start) / (total_minutes * 60))
            lr = 3e-4 * (0.15 + 0.85 * 0.5 * (1 + np.cos(np.pi * frac)))
            ent_coef = 0.012 * (1 - frac) + 0.002 * frac
            for g in opt.param_groups:
                g["lr"] = lr

            # --- collecte ---------------------------------------------------
            episodes, stats = [], defaultdict(lambda: [0.0, 0])
            for c in conns:
                eps, st = c.recv()
                episodes.extend(eps)
                for k2, (s, n) in st.items():
                    stats[k2][0] += s
                    stats[k2][1] += n
            t_collect = time.monotonic() - t_sent
            w, t_sent = send_collect(it + 1)
            for i in league_ids:
                key = f"L{i}"
                if key in stats and stats[key][1] > 0:
                    sc = (stats[key][0] / stats[key][1] + 1) / 2
                    league_score[i] = 0.8 * league_score.get(i, 0.5) + 0.2 * sc

            if not episodes:
                print(f"iter {it} : aucune transition collectée, on passe", flush=True)
                continue

            # --- GAE avec critique privilégié -------------------------------
            obs = np.concatenate([e[0] for e in episodes])
            priv = np.concatenate([e[1] for e in episodes])
            mask = np.concatenate([e[2] for e in episodes])
            act = np.concatenate([e[3] for e in episodes])
            logp_old = np.concatenate([e[4] for e in episodes])
            x_c = torch.as_tensor(np.concatenate([obs, priv], axis=1), device=device)
            with torch.no_grad():
                values = torch.cat([critic(x_c[i : i + 16384]) for i in range(0, len(x_c), 16384)]).cpu().numpy()
            adv = np.zeros(len(obs), dtype=np.float32)
            ret = np.zeros(len(obs), dtype=np.float32)
            pos = 0
            for e in episodes:
                T = len(e[0])
                v = values[pos : pos + T]
                last = 0.0
                for t in reversed(range(T)):
                    r = e[5] if t == T - 1 else 0.0
                    nv = 0.0 if t == T - 1 else v[t + 1]
                    delta = r + gamma * nv - v[t]
                    last = delta + gamma * lam * last
                    adv[t + pos] = last
                ret[pos : pos + T] = adv[pos : pos + T] + v
                pos += T

            # --- PPO --------------------------------------------------------
            n = len(obs)
            adv_t = torch.as_tensor((adv - adv.mean()) / (adv.std() + 1e-6), device=device)
            obs_t = torch.as_tensor(obs, device=device)
            mask_t = torch.as_tensor(mask, device=device)
            act_t = torch.as_tensor(act, device=device)
            logp_t = torch.as_tensor(logp_old, device=device)
            ret_t = torch.as_tensor(ret, device=device)
            val_t = torch.as_tensor(values, device=device)
            kls, ents = [], []
            bs = 4096
            for _ in range(3):
                idx = torch.randperm(n, device=device)
                for s in range(0, n, bs):
                    b = idx[s : s + bs]
                    logits = actor(obs_t[b], mask_t[b])
                    dist = torch.distributions.Categorical(logits=logits)
                    logp = dist.log_prob(act_t[b])
                    ratio = torch.exp(logp - logp_t[b])
                    pi_loss = -torch.min(ratio * adv_t[b], torch.clamp(ratio, 1 - clip, 1 + clip) * adv_t[b]).mean()
                    vpred = critic(x_c[b])
                    v_clipped = val_t[b] + torch.clamp(vpred - val_t[b], -clip, clip)
                    v_loss = torch.max((vpred - ret_t[b]) ** 2, (v_clipped - ret_t[b]) ** 2).mean()
                    ent = dist.entropy().mean()
                    loss = pi_loss + 0.5 * v_loss - ent_coef * ent
                    opt.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(params, 0.5)
                    opt.step()
                    kls.append(float((logp_t[b] - logp.detach()).mean()))
                    ents.append(float(ent.detach()))
            el = (time.monotonic() - start) / 60

            def avg(key):
                s, c = stats.get(key, (0.0, 0))
                return s / c if c else float("nan")

            lg = [league_score[i] for i in league_ids]
            print(
                f"iter {it} n={n} eps={len(episodes)} t={el:.1f}min collect={t_collect:.1f}s "
                f"lr={lr:.1e} ent={np.mean(ents):.3f} kl={np.mean(kls):.4f} "
                f"r_eco={avg('eco'):+.2f} r_rand={avg('rand'):+.2f} r_mixed={avg('mixed'):+.2f} "
                f"ligue={len(league_ids)} pfsp_min={min(lg) if lg else float('nan'):.2f}",
                flush=True,
            )
            torch.save({"actor": actor.state_dict(), "critic": critic.state_dict(), "it": it}, args.out + ".last.pt")

            # --- ligue ------------------------------------------------------
            w = actor.numpy_weights()  # poids à jour (ceux envoyés aux workers ont une itération de retard)
            if it % args.league_every == 0:
                lid = it
                np.savez(f"{args.out}_league/{lid}.npz", **w)
                league_ids.append(lid)
                for c in conns:
                    c.send({"cmd": "league_add", "id": lid, "weights": w})
                if len(league_ids) > 24:
                    # On garde les 8 plus anciens un sur deux (ancrage) et les récents.
                    drop = league_ids[8]
                    league_ids.remove(drop)
                    for c in conns:
                        c.send({"cmd": "league_drop", "id": drop})

            # --- éval -------------------------------------------------------
            if it % args.eval_every == 0:
                t0 = time.monotonic()
                wr_r, _ = eval_vs(w, Rand(), 200, seed0=it)
                wr_e, _ = eval_vs(w, SaveSpecials(), 300, seed0=it + 1)
                wr_v1 = eval_vs(w, None, 300, seed0=it + 2, v1=v1)[0] if v1 else 0.5
                wr_4, r_4 = eval_vs(w, SaveSpecials(), 120, seed0=it + 3, n_players=4)
                print(
                    f"EVAL it={it} t={el:5.1f}min vs_hasard={wr_r:6.1%} vs_econome={wr_e:6.1%} "
                    f"vs_v1={wr_v1:6.1%} table4_vs_econome={wr_4:6.1%} (r={r_4:+.2f}) "
                    f"({time.monotonic() - t0:.0f}s)",
                    flush=True,
                )
                score = wr_e + wr_v1 + 0.5 * wr_4
                if score > best:
                    best = score
                    np.savez(args.out + ".npz", **w)
                    torch.save({"actor": actor.state_dict(), "critic": critic.state_dict(), "it": it}, args.out + ".best.pt")
                    print(f"SAVE  it={it} score={score:.3f}", flush=True)
    finally:
        for c in conns:
            try:
                c.recv()  # collecte en vol
                c.send({"cmd": "stop"})
            except Exception:
                pass
    print("FIN entraînement v2", flush=True)


if __name__ == "__main__":
    main()
