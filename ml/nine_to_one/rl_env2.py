"""Environnement RL v2 du Nine to One : 2 à 5 joueurs, information imparfaite honnête.

Différences avec rl_env (v1) :
- N joueurs (2..5) ; l'observation décrit jusqu'à 4 adversaires dans l'ordre du
  tour, chacun avec ses visibles, sa mémoire publique et ses tailles.
- Vrai comptage de cartes : distribution des cartes dont la position est
  inconnue (52 − tout ce qui a été vu), défausse vue, tas complet.
- Mémoire publique séquentielle (ramassage = tout le tas, carte retournée,
  poses) partagée telle quelle avec le backend (app/bots.py v2).
- Récompense par rang : +1 premier sorti, −1 dernier, linéaire entre les deux.
- Vue privilégiée (mains adverses, cachées, pioche) réservée au critique
  pendant l'entraînement : jamais utilisée par la politique.

Une décision = (valeur, une/toutes, direction si 7) parmi les coups légaux.
Les retournements aveugles sont aléatoires ; l'enchaînement « bonne pioche »
est automatique (carte piochée identique, ou cachée retournée vite).
"""

import random
import sys

import numpy as np
from pathlib import Path

# Chemins relatifs au repo : ce dossier (ml/nine_to_one) et le backend.
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"

sys.path.insert(0, str(BACKEND))

from app.games.nine_to_one.engine import (  # noqa: E402
    GameStatus,
    add_player,
    chase_flip,
    chase_play,
    chase_value,
    create_game,
    flip_face_down,
    play_cards,
    playable_values,
    set_ready,
    swap_cards,
)
from app.games.nine_to_one.engine.state import Comparator  # noqa: E402

N_VALUES = 13  # 2..14
N_ACTIONS = 52  # valeur(13) × mode(1|tout) × direction(>=|<=)
MAX_PLAYERS = 5
SLOTS = MAX_PLAYERS - 1  # adversaires décrits, dans l'ordre du tour après moi

# Blocs de l'observation (tous en float32).
SELF_DIM = 13 + 13  # main, visibles
TABLE_DIM = 13 + 13 + 13 + 14 + 1  # non vues, tas, défausse vue, sommet one-hot, série
SLOT_DIM = 13 + 13 + 6  # visibles, mémoire, [présent, actif, main/10, cachées/3, prochain, dernier poseur]
SCALARS_DIM = 15
OBS_DIM = SELF_DIM + TABLE_DIM + SLOTS * SLOT_DIM + SCALARS_DIM  # 13*2+54+4*32+15 = 223
PRIV_DIM = SLOTS * 13 + MAX_PLAYERS * 13 + 13  # mains adverses, cachées de tous, pioche = 130

SWAP_SCORE = {2: 15, 10: 14, 14: 13, 13: 12, 12: 11, 11: 10, 9: 9, 7: 8, 8: 6, 6: 3, 5: 2, 4: 1.5, 3: 1}


def counts13(cards):
    v = np.zeros(N_VALUES, dtype=np.float32)
    for c in cards:
        v[c.value - 2] += 1
    return v


def decode_action(a):
    value = 2 + (a % 13)
    mode_all = (a // 13) % 2 == 1
    direction = Comparator.LTE if (a // 26) % 2 == 1 else Comparator.GTE
    return value, mode_all, direction


def smart_swap(state, seat):
    player = state.players[seat]
    for _ in range(6):
        worst = min(range(len(player.face_up)), key=lambda i: SWAP_SCORE[player.face_up[i].value])
        best = max(range(len(player.hand)), key=lambda i: SWAP_SCORE[player.hand[i].value])
        if SWAP_SCORE[player.hand[best].value] > SWAP_SCORE[player.face_up[worst].value]:
            swap_cards(state, seat, best, worst)
        else:
            break


class Memory:
    """Ce qu'un observateur attentif sait depuis les événements publics.

    known[s] : cartes (par valeur) dont on sait qu'elles sont dans la main de s.
    discard : cartes parties à la défausse (coupes). pile : suivi du tas pendant
    le traitement d'un lot d'événements (resynchronisé sur le vrai tas ensuite).
    """

    def __init__(self, n_players):
        self.n = n_players
        self.known = np.zeros((n_players, N_VALUES), dtype=np.float32)
        self.discard = np.zeros(N_VALUES, dtype=np.float32)
        self.pile = np.zeros(N_VALUES, dtype=np.float32)

    def copy(self):
        m = Memory(self.n)
        m.known = self.known.copy()
        m.discard = self.discard.copy()
        m.pile = self.pile.copy()
        return m

    def on_events(self, events, pile_after):
        """`events` : lot renvoyé par un appel moteur ; `pile_after` : compte du tas après."""
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


def rank_reward(rank, n):
    return 1.0 - 2.0 * (rank - 1) / (n - 1)


class Game:
    """Une partie N joueurs pilotée décision par décision."""

    def __init__(self, seed, n_players=None, max_steps=600):
        self.rng = random.Random(seed)
        n = n_players or self.rng.choice([2, 2, 3, 3, 4, 5])
        self.n = n
        self.state = create_game("P0", seed=seed)
        for i in range(1, n):
            add_player(self.state, f"P{i}")
        for s in range(n):
            # Diversité de mises en place : la plupart optimisent, certains laissent tel quel.
            if self.rng.random() < 0.8:
                smart_swap(self.state, s)
        for s in range(n):
            set_ready(self.state, s)
        self.mem = Memory(n)
        self.steps = 0
        self.max_steps = max_steps
        self._to_decision()

    @classmethod
    def from_state(cls, state, mem, rng, max_steps=600):
        """Enveloppe une partie déjà en cours (simulation de recherche, backend)."""
        game = cls.__new__(cls)
        game.rng = rng
        game.n = len(state.players)
        game.state = state
        game.mem = mem
        game.steps = 0
        game.max_steps = max_steps
        return game

    # ------------------------------------------------------------------
    def _apply(self, events):
        self.mem.on_events(events, counts13(self.state.pile))

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

    # ------------------------------------------------------------------
    @property
    def done(self):
        return self.state.status is not GameStatus.PLAYING or self.steps >= self.max_steps

    def result(self, seat):
        if self.state.status is not GameStatus.FINISHED:
            return 0.0
        return rank_reward(self.state.players[seat].finish_rank, self.n)

    @property
    def seat(self):
        return self.state.turn_index

    def step(self, action):
        seat = self.state.turn_index
        value, mode_all, direction = decode_action(action)
        me = self.state.players[seat]
        copies = sum(1 for c in me.hand if c.value == value)
        if copies == len(me.hand):
            copies += sum(1 for c in me.face_up if c.value == value)
        self.step_raw(value, copies if mode_all else 1, direction if value == 7 else None)

    def step_raw(self, value, count, direction):
        seat = self.state.turn_index
        self._apply(play_cards(self.state, seat, value, count, direction))
        self._auto_chase(seat)
        self.steps += 1
        self._to_decision()

    # ------------------------------------------------------------------
    # Observation honnête (tout est reconstructible depuis la vue publique)
    # ------------------------------------------------------------------

    def obs_mask(self, seat=None):
        state = self.state
        seat = state.turn_index if seat is None else seat
        me = state.players[seat]
        n = self.n
        mem = self.mem

        my_hand = counts13(me.hand)
        my_up = counts13(me.face_up)
        pile = counts13(state.pile)
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

        slots = np.zeros((SLOTS, SLOT_DIM), dtype=np.float32)
        others_up = np.zeros(N_VALUES, dtype=np.float32)
        known_total = np.zeros(N_VALUES, dtype=np.float32)
        next_active = self._next_active(seat)
        for k in range(1, n):
            o = (seat + k) % n
            op = state.players[o]
            up = counts13(op.face_up)
            others_up += up
            known = mem.known[o]
            known_total += known
            slots[k - 1, :13] = up
            slots[k - 1, 13:26] = known / 4.0
            slots[k - 1, 26:] = [
                1.0,
                0.0 if op.finished else 1.0,
                len(op.hand) / 10.0,
                len(op.face_down) / 3.0,
                1.0 if o == next_active else 0.0,
                1.0 if state.last_play_index == o else 0.0,
            ]
        # Cartes dont la position est inconnue : ni chez moi, ni visibles, ni sur le
        # tas, ni coupées, ni connues dans une main adverse (mémoire).
        unseen = 4.0 - my_hand - my_up - others_up - pile - mem.discard - np.minimum(known_total, 4.0)
        unseen = np.clip(unseen, 0.0, 4.0)

        cons = state.constraint
        active = len(state.active_indices())
        scalars = np.array(
            [
                len(me.hand) / 10.0,
                len(me.face_up) / 3.0,
                len(me.face_down) / 3.0,
                len(state.pile) / 15.0,
                len(state.draw_pile) / 34.0,
                1.0 if len(state.draw_pile) == 0 else 0.0,
                run / 4.0,
                1.0 if cons and cons.comparator is Comparator.GTE else 0.0,
                1.0 if cons and cons.comparator is Comparator.LTE and cons.value == 7 else 0.0,
                1.0 if cons and cons.comparator is Comparator.LTE and cons.value == 9 else 0.0,
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
        for v in playable_values(state, seat):
            i = v - 2
            copies = sum(1 for c in me.hand if c.value == v)
            if copies == len(me.hand):
                copies += sum(1 for c in me.face_up if c.value == v)
            for d in (0, 1) if v == 7 else (0,):
                mask[d * 26 + 13 + i] = True  # tout poser
                if copies > 1:
                    mask[d * 26 + i] = True  # une seule
        return obs, mask, seat

    def priv(self, seat=None):
        """Vue privilégiée pour le critique : mains adverses, cachées, pioche."""
        state = self.state
        seat = state.turn_index if seat is None else seat
        n = self.n
        hands = np.zeros((SLOTS, N_VALUES), dtype=np.float32)
        downs = np.zeros((MAX_PLAYERS, N_VALUES), dtype=np.float32)
        downs[0] = counts13(state.players[seat].face_down)
        for k in range(1, n):
            o = (seat + k) % n
            hands[k - 1] = counts13(state.players[o].hand)
            downs[k] = counts13(state.players[o].face_down)
        return np.concatenate([hands.reshape(-1) / 4.0, downs.reshape(-1) / 4.0, counts13(state.draw_pile) / 4.0])

    def _next_active(self, seat):
        for step in range(1, self.n + 1):
            cand = (seat + step) % self.n
            if cand != seat and not self.state.players[cand].finished:
                return cand
        return None


if __name__ == "__main__":
    import time

    t0 = time.monotonic()
    steps = 0
    rng = random.Random(0)
    for g in range(200):
        game = Game(g)
        while not game.done:
            obs, mask, seat = game.obs_mask()
            assert obs.shape == (OBS_DIM,) and game.priv().shape == (PRIV_DIM,)
            game.step(int(rng.choice(np.flatnonzero(mask))))
            steps += 1
    dt = time.monotonic() - t0
    print(f"200 parties, {steps} décisions en {dt:.1f}s ({steps / dt:.0f} décisions/s)")
