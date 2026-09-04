"""Cerveau v2 des bots : observation honnête, réseau numpy, recherche déterminisée.

Miroir exact de ml/rl_env2.py (observation, mémoire) et de ml/search.py (recherche),
sans torch. Tout part d'un « instantané public » (Snapshot) : ce qu'un joueur
voit depuis son siège. Deux fabriques le produisent, depuis la vue WebSocket
(décision réelle) ou depuis un GameState de simulation (recherche, où les
cartes cachées ont été redistribuées au hasard : rien de réel n'y fuit).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.engine import (
    Comparator,
    GameError,
    GameState,
    GameStatus,
    chase_flip,
    chase_play,
    chase_value,
    flip_face_down,
    play_cards,
    playable_values,
)

N_VALUES = 13
N_ACTIONS = 52
MAX_PLAYERS = 5
SLOTS = MAX_PLAYERS - 1
SLOT_DIM = 32
OBS_DIM = 26 + 54 + SLOTS * SLOT_DIM + 15  # 223
PRIV_DIM = SLOTS * 13 + MAX_PLAYERS * 13 + 13  # 130
LN_EPS = 1e-5


def counts13(values) -> np.ndarray:
    v = np.zeros(N_VALUES, dtype=np.float32)
    for x in values:
        v[x - 2] += 1
    return v


def decode_action(a: int) -> tuple[int, bool, Comparator]:
    value = 2 + (a % 13)
    mode_all = (a // 13) % 2 == 1
    direction = Comparator.LTE if (a // 26) % 2 == 1 else Comparator.GTE
    return value, mode_all, direction


# ---------------------------------------------------------------------------
# Mémoire publique (identique à rl_env2.Memory)
# ---------------------------------------------------------------------------


class Memory:
    def __init__(self, n_players: int) -> None:
        self.n = n_players
        self.known = np.zeros((n_players, N_VALUES), dtype=np.float32)
        self.discard = np.zeros(N_VALUES, dtype=np.float32)
        self.pile = np.zeros(N_VALUES, dtype=np.float32)

    def copy(self) -> Memory:
        m = Memory(self.n)
        m.known = self.known.copy()
        m.discard = self.discard.copy()
        m.pile = self.pile.copy()
        return m

    def on_events(self, events: list[dict], pile_after: np.ndarray) -> None:
        for e in events:
            t = e["type"]
            if t == "cards_played":
                for cd in e["cards"]:
                    i = cd["value"] - 2
                    self.pile[i] += 1
                    if self.known[e["player"], i] > 0:
                        self.known[e["player"], i] -= 1
            elif t == "card_flipped":
                self.known[e["player"], e["card"]["value"] - 2] += 1
            elif t == "pile_picked_up":
                self.known[e["player"]] += self.pile
                self.pile[:] = 0
            elif t == "pile_cut":
                self.discard += self.pile
                self.pile[:] = 0
        self.pile = pile_after.copy()


# ---------------------------------------------------------------------------
# Instantané public et observation
# ---------------------------------------------------------------------------


@dataclass
class Snapshot:
    seat: int
    n: int
    hand: list[int]  # valeurs de ma main
    face_up: list[list[int]]  # par siège
    hand_count: list[int]
    face_down_count: list[int]
    finished: list[bool]
    pile: list[int]
    constraint: tuple[str, int] | None
    draw_count: int
    last_play: int | None
    playable: list[int] = field(default_factory=list)


def snapshot_from_view(view: dict) -> Snapshot:
    ps = view["players"]
    me = ps[view["your_seat"]]
    cons = view["constraint"]
    return Snapshot(
        seat=view["your_seat"],
        n=len(ps),
        hand=[c["value"] for c in me["hand"]],
        face_up=[[c["value"] for c in p["face_up"]] for p in ps],
        hand_count=[p["hand_count"] for p in ps],
        face_down_count=[p["face_down_count"] for p in ps],
        finished=[p["finish_rank"] is not None for p in ps],
        pile=[c["value"] for c in view["pile"]],
        constraint=(cons["comparator"], cons["value"]) if cons else None,
        draw_count=view["draw_count"],
        last_play=view["last_play_seat"],
        playable=list(view["playable_values"]),
    )


def snapshot_from_state(state: GameState, seat: int) -> Snapshot:
    ps = state.players
    cons = state.constraint
    return Snapshot(
        seat=seat,
        n=len(ps),
        hand=[c.value for c in ps[seat].hand],
        face_up=[[c.value for c in p.face_up] for p in ps],
        hand_count=[len(p.hand) for p in ps],
        face_down_count=[len(p.face_down) for p in ps],
        finished=[p.finished for p in ps],
        pile=[c.value for c in state.pile],
        constraint=(cons.comparator.value, cons.value) if cons else None,
        draw_count=len(state.draw_pile),
        last_play=state.last_play_index,
        playable=sorted(playable_values(state, seat)),
    )


def copies_of(snap: Snapshot, value: int) -> int:
    n = sum(1 for v in snap.hand if v == value)
    if n == len(snap.hand):
        n += sum(1 for v in snap.face_up[snap.seat] if v == value)
    return n


def obs_mask(snap: Snapshot, mem: Memory) -> tuple[np.ndarray, np.ndarray]:
    """Observation 223 dims + masque 52 actions, exactement rl_env2.Game.obs_mask."""
    seat, n = snap.seat, snap.n
    my_hand = counts13(snap.hand)
    my_up = counts13(snap.face_up[seat])
    pile = counts13(snap.pile)
    top = snap.pile[-1] if snap.pile else None
    top_onehot = np.zeros(14, dtype=np.float32)
    top_onehot[(top - 2) if top else 13] = 1.0
    run = 0
    if top:
        run = 1
        for v in reversed(snap.pile[:-1]):
            if v == top:
                run += 1
            else:
                break
    next_active = None
    for step in range(1, n + 1):
        cand = (seat + step) % n
        if cand != seat and not snap.finished[cand]:
            next_active = cand
            break
    slots = np.zeros((SLOTS, SLOT_DIM), dtype=np.float32)
    others_up = np.zeros(N_VALUES, dtype=np.float32)
    known_total = np.zeros(N_VALUES, dtype=np.float32)
    for k in range(1, n):
        o = (seat + k) % n
        up = counts13(snap.face_up[o])
        others_up += up
        known_total += mem.known[o]
        slots[k - 1, :13] = up
        slots[k - 1, 13:26] = mem.known[o] / 4.0
        slots[k - 1, 26:] = [
            1.0,
            0.0 if snap.finished[o] else 1.0,
            snap.hand_count[o] / 10.0,
            snap.face_down_count[o] / 3.0,
            1.0 if o == next_active else 0.0,
            1.0 if snap.last_play == o else 0.0,
        ]
    unseen = 4.0 - my_hand - my_up - others_up - pile - mem.discard - np.minimum(known_total, 4.0)
    unseen = np.clip(unseen, 0.0, 4.0)
    cons = snap.constraint
    active = sum(1 for f in snap.finished if not f)
    scalars = np.array(
        [
            len(snap.hand) / 10.0,
            len(snap.face_up[seat]) / 3.0,
            snap.face_down_count[seat] / 3.0,
            len(snap.pile) / 15.0,
            snap.draw_count / 34.0,
            1.0 if snap.draw_count == 0 else 0.0,
            run / 4.0,
            1.0 if cons and cons[0] == ">=" else 0.0,
            1.0 if cons and cons[0] == "<=" and cons[1] == 7 else 0.0,
            1.0 if cons and cons[0] == "<=" and cons[1] == 9 else 0.0,
            1.0 if n == 2 else 0.0,
            1.0 if n == 3 else 0.0,
            1.0 if n == 4 else 0.0,
            1.0 if n == 5 else 0.0,
            active / 5.0,
        ],
        dtype=np.float32,
    )
    obs = np.concatenate(
        [
            my_hand,
            my_up,
            unseen / 4.0,
            pile / 4.0,
            mem.discard / 4.0,
            top_onehot,
            np.array([run / 4.0], dtype=np.float32),
            slots.reshape(-1),
            scalars,
        ]
    )
    mask = np.zeros(N_ACTIONS, dtype=bool)
    for v in snap.playable:
        i = v - 2
        copies = copies_of(snap, v)
        for d in (0, 1) if v == 7 else (0,):
            mask[d * 26 + 13 + i] = True
            if copies > 1:
                mask[d * 26 + i] = True
    return obs, mask


def priv_from_state(state: GameState, seat: int) -> np.ndarray:
    """Vue privilégiée du critique (uniquement sur un état de simulation)."""
    n = len(state.players)
    hands = np.zeros((SLOTS, N_VALUES), dtype=np.float32)
    downs = np.zeros((MAX_PLAYERS, N_VALUES), dtype=np.float32)
    downs[0] = counts13(c.value for c in state.players[seat].face_down)
    for k in range(1, n):
        o = (seat + k) % n
        hands[k - 1] = counts13(c.value for c in state.players[o].hand)
        downs[k] = counts13(c.value for c in state.players[o].face_down)
    draw = counts13(c.value for c in state.draw_pile)
    return np.concatenate([hands.reshape(-1) / 4.0, downs.reshape(-1) / 4.0, draw / 4.0])


# ---------------------------------------------------------------------------
# Réseaux numpy (acteur + critique)
# ---------------------------------------------------------------------------


def _layernorm(h, g, b):
    mu = h.mean(-1, keepdims=True)
    var = ((h - mu) ** 2).mean(-1, keepdims=True)
    return (h - mu) / np.sqrt(var + LN_EPS) * g + b


def actor_logits(w: dict, x: np.ndarray) -> np.ndarray:
    h = np.maximum(_layernorm(x @ w["w1"].T + w["b1"], w["g1"], w["be1"]), 0.0)
    h = np.maximum(_layernorm(h @ w["w2"].T + w["b2"], w["g2"], w["be2"]), 0.0)
    h = np.maximum(h @ w["w3"].T + w["b3"], 0.0)
    return h @ w["wpi"].T + w["bpi"]


def critic_value(wc: dict, x: np.ndarray) -> float:
    h = np.maximum(_layernorm(x @ wc["w1"].T + wc["b1"], wc["g1"], wc["be1"]), 0.0)
    h = np.maximum(_layernorm(h @ wc["w2"].T + wc["b2"], wc["g2"], wc["be2"]), 0.0)
    h = np.maximum(h @ wc["w3"].T + wc["b3"], 0.0)
    return float(h[0] @ wc["wv"][0] + wc["bv"][0])


def load_npz(name: str) -> dict:
    with np.load(Path(__file__).with_name(name)) as f:
        return {k: f[k] for k in f.files}


class Brain:
    """Acteur + critique v2 chargés une fois (lazy)."""

    _actor: dict | None = None
    _critic: dict | None = None

    @classmethod
    def actor(cls) -> dict:
        if cls._actor is None:
            cls._actor = load_npz("bot_policy_v2.npz")
        return cls._actor

    @classmethod
    def critic(cls) -> dict:
        if cls._critic is None:
            cls._critic = load_npz("bot_policy_v2_critic.npz")
        return cls._critic

    @classmethod
    def load(cls, actor_path: str, critic_path: str) -> None:
        """Force d'autres poids (outils d'évaluation hors ligne : ml/ladder.py)."""
        with np.load(actor_path) as f:
            cls._actor = {k: f[k] for k in f.files}
        with np.load(critic_path) as f:
            cls._critic = {k: f[k] for k in f.files}


def greedy_action(snap: Snapshot, mem: Memory) -> int:
    obs, mask = obs_mask(snap, mem)
    logits = actor_logits(Brain.actor(), obs[None])[0]
    return int(np.argmax(np.where(mask, logits, -1e9)))


# ---------------------------------------------------------------------------
# Simulation (recherche) : même déroulé que rl_env2.Game
# ---------------------------------------------------------------------------


class Sim:
    def __init__(self, state: GameState, mem: Memory, rng: random.Random) -> None:
        self.state, self.mem, self.rng = state, mem, rng
        self.n = len(state.players)
        self._to_decision()

    def _apply(self, events):
        self.mem.on_events(events, counts13(c.value for c in self.state.pile))

    def _auto_chase(self, seat):
        guard = 0
        while self.state.status is GameStatus.PLAYING and guard < 8:
            guard += 1
            if chase_value(self.state, seat) is None:
                break
            p = self.state.players[seat]
            if p.hand:
                self._apply(chase_play(self.state, seat, 1))
            elif p.face_down:
                self._apply(chase_flip(self.state, seat, self.rng.randrange(len(p.face_down))))
            else:
                break

    def _to_decision(self):
        while self.state.status is GameStatus.PLAYING:
            seat = self.state.turn_index
            p = self.state.players[seat]
            if p.hand:
                return
            self._apply(flip_face_down(self.state, seat, self.rng.randrange(len(p.face_down))))
            self._auto_chase(seat)

    @property
    def done(self):
        return self.state.status is not GameStatus.PLAYING

    def step(self, action: int) -> None:
        seat = self.state.turn_index
        value, mode_all, direction = decode_action(action)
        snap = snapshot_from_state(self.state, seat)
        count = copies_of(snap, value) if mode_all else 1
        self._apply(play_cards(self.state, seat, value, count, direction if value == 7 else None))
        self._auto_chase(seat)
        self._to_decision()

    def result(self, seat: int) -> float:
        rank = self.state.players[seat].finish_rank
        if self.state.status is not GameStatus.FINISHED or rank is None:
            return 0.0
        return 1.0 - 2.0 * (rank - 1) / (self.n - 1)


def determinize(state: GameState, mem: Memory, seat: int, rng: random.Random) -> GameState:
    """Copie où les cartes invisibles pour `seat` sont redistribuées au hasard,
    en plaçant d'abord les valeurs connues (mémoire) dans les mains adverses."""
    sim = GameState.from_dict(state.to_dict())
    hidden = []
    for i, p in enumerate(sim.players):
        if i != seat:
            hidden.extend(p.hand)
        hidden.extend(p.face_down)
    hidden.extend(sim.draw_pile)
    rng.shuffle(hidden)
    pool = list(hidden)
    for i, p in enumerate(sim.players):
        if i == seat:
            continue
        hand = []
        for v in range(N_VALUES):
            for _ in range(int(min(mem.known[i, v], 4))):
                j = next((k for k, c in enumerate(pool) if c.value == v + 2), None)
                if j is None or len(hand) >= len(p.hand):
                    break
                hand.append(pool.pop(j))
        while len(hand) < len(p.hand):
            hand.append(pool.pop())
        p.hand = sorted(hand, key=lambda c: (c.value, c.suit.value))
    for p in sim.players:
        p.face_down = [pool.pop() for _ in p.face_down]
    sim.draw_pile = [pool.pop() for _ in sim.draw_pile]
    return sim


STUCK = [0]  # simulations abandonnées faute de coup légal (diagnostic)


def rollout_value(
    sim: Sim, seat: int, w: dict, wc: dict, horizon: int, rng: random.Random
) -> float:
    steps = 0
    while not sim.done and steps < horizon:
        s = sim.state.turn_index
        obs, mask = obs_mask(snapshot_from_state(sim.state, s), sim.mem)
        if not mask.any():
            # Position sans coup légal : on évalue la feuille plutôt que de tirer
            # une action au hasard. Ne doit pas arriver ; garde-fou.
            STUCK[0] += 1
            break
        logits = np.where(mask, actor_logits(w, obs[None])[0], -1e9)
        z = logits - logits.max()
        p = np.exp(z) * mask
        p /= p.sum()
        sim.step(int(rng.choices(range(N_ACTIONS), p)[0]))
        steps += 1
    if sim.state.status is GameStatus.FINISHED:
        return sim.result(seat)
    if sim.done:
        return 0.0
    obs, _ = obs_mask(snapshot_from_state(sim.state, seat), sim.mem)
    return critic_value(wc, np.concatenate([obs, priv_from_state(sim.state, seat)])[None])


C_PUCT = 2.0


def search_action(
    state: GameState,
    mem: Memory,
    seat: int,
    rng: random.Random,
    n_sims: int = 220,
    horizon: int = 30,
    time_budget: float = 0.8,
) -> int:
    """Meilleur coup par recherche déterminisée guidée (miroir de ml/search.py).

    Chaque simulation tire une donne plausible des cartes cachées (déterminisation
    respectant la mémoire publique), joue un coup candidat, puis déroule la partie
    avec le réseau ; la feuille est évaluée par le critique. Les simulations sont
    allouées par un bandit PUCT guidé par la politique : les coups prometteurs sont
    approfondis, les mauvais abandonnés — bien plus efficace qu'une grille uniforme.

    `n_sims` est un plafond : la recherche s'arrête à `time_budget` secondes, après
    au moins un tour complet de tous les coups candidats.
    """
    w, wc = Brain.actor(), Brain.critic()
    snap = snapshot_from_state(state, seat)
    obs, mask = obs_mask(snap, mem)
    logits = np.where(mask, actor_logits(w, obs[None])[0], -1e9)
    acts = [int(a) for a in np.flatnonzero(mask)]
    if len(acts) == 1:
        return acts[0]
    logp = logits - logits.max()
    logp = logp - np.log(np.exp(logp).sum())
    prior = np.exp(logp[acts])

    total = np.zeros(len(acts))  # somme des valeurs simulées
    visits = np.zeros(len(acts))
    deadline = time.monotonic() + time_budget
    det = None
    for i in range(n_sims):
        if i % len(acts) == 0:
            if i > 0 and time.monotonic() > deadline:
                break
            det = determinize(state, mem, seat, rng)  # une donne par tour de bandit
        if i < len(acts):
            k = i  # un essai garanti par coup candidat
        else:
            q = np.where(visits > 0, total / np.maximum(visits, 1.0), 0.0)
            u = C_PUCT * prior * np.sqrt(visits.sum()) / (1.0 + visits)
            k = int(np.argmax(q + u))
        sim = Sim(GameState.from_dict(det.to_dict()), mem.copy(), random.Random(rng.random()))
        try:
            sim.step(acts[k])
        except GameError:
            # Donne incohérente pour ce coup : elle ne vote pas.
            STUCK[0] += 1
            continue
        total[k] += rollout_value(sim, seat, w, wc, horizon, rng)
        visits[k] += 1
    q = np.where(visits > 0, total / np.maximum(visits, 1.0), -1.0)
    return acts[int(np.argmax(q + 0.5 * logp[acts]))]
