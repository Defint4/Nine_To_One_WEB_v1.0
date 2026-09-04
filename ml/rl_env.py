"""Environnement RL du Nine to One (2 joueurs, information imparfaite honnête).

Une décision = choisir (valeur, tout/une seule, direction si 7) parmi les coups
légaux. Les retournements de cartes cachées sont aveugles (aléatoires, pas de
décision) et l'enchaînement « bonne pioche » est automatique.

L'observation d'un siège ne contient QUE : sa main, ses visibles + cachées
(compte), les visibles adverses, la taille de main adverse, la mémoire des
cartes adverses vues (ramassages/retournements publics), le tas, la défausse
vue, la contrainte, les tailles de pioche.
"""

import random
import sys

import numpy as np

sys.path.insert(0, "/home/defint/projects/nine_to_one/backend")

from app.engine import (  # noqa: E402
    GameStatus,
    add_player,
    chase_play,
    chase_value,
    create_game,
    flip_face_down,
    play_cards,
    playable_values,
    set_ready,
    swap_cards,
)
from app.engine.state import Comparator  # noqa: E402

N_VALUES = 13  # 2..14
OBS_DIM = 13 * 5 + 14 + 12  # mains/visibles/mémoire/défausse + top onehot + scalaires
N_ACTIONS = 52  # valeur(13) × mode(1|tout) × direction(GE|LE)

SWAP_SCORE = {2: 15, 10: 14, 14: 13, 13: 12, 12: 11, 11: 10, 9: 9, 7: 8, 8: 6, 6: 3, 5: 2, 4: 1.5, 3: 1}


def smart_swap(state, seat):
    player = state.players[seat]
    for _ in range(6):
        worst = min(range(len(player.face_up)), key=lambda i: SWAP_SCORE[player.face_up[i].value])
        best = max(range(len(player.hand)), key=lambda i: SWAP_SCORE[player.hand[i].value])
        if SWAP_SCORE[player.hand[best].value] > SWAP_SCORE[player.face_up[worst].value]:
            swap_cards(state, seat, best, worst)
        else:
            break


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


class Game:
    """Une partie 2 joueurs pilotée décision par décision."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.state = create_game("A", seed=seed)
        add_player(self.state, "B")
        for s in (0, 1):
            smart_swap(self.state, s)
        for s in (0, 1):
            set_ready(self.state, s)
        # Mémoire honnête : valeurs connues dans la main adverse + défausse vue.
        self.known = [np.zeros(N_VALUES, dtype=np.float32) for _ in (0, 1)]
        self.seen_gone = np.zeros(N_VALUES, dtype=np.float32)  # coupées (défausse)
        self.steps = 0
        self._to_decision()

    # ------------------------------------------------------------------
    def _on_events(self, events, pile_before):
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
                # les cartes posées dans ce lot sont aussi parties : approx incluse
                for pe in events:
                    if pe["type"] == "cards_played":
                        for cd in pe["cards"]:
                            self.seen_gone[cd["value"] - 2] += 1

    def _auto_chase(self, seat):
        guard = 0
        while self.state.status is GameStatus.PLAYING and guard < 6:
            guard += 1
            if chase_value(self.state, seat) is None:
                break
            p = self.state.players[seat]
            if not p.hand:
                break  # pas d'enchaînement aveugle automatique
            pile_before = counts13(self.state.pile)
            events = chase_play(self.state, seat, 1)
            self._on_events(events, pile_before)

    def _to_decision(self):
        """Avance jusqu'à une vraie décision (main non vide) ou la fin."""
        while self.state.status is GameStatus.PLAYING:
            seat = self.state.turn_index
            p = self.state.players[seat]
            if p.hand:
                return
            pile_before = counts13(self.state.pile)
            events = flip_face_down(self.state, seat, self.rng.randrange(len(p.face_down)))
            self._on_events(events, pile_before)
            self._auto_chase(seat)

    # ------------------------------------------------------------------
    @property
    def done(self):
        return self.state.status is not GameStatus.PLAYING or self.steps >= 500

    def result(self, seat):
        if self.state.status is not GameStatus.FINISHED:
            return 0.0  # partie plafonnée : nul
        return 1.0 if self.state.players[seat].finish_rank == 1 else -1.0

    def obs_mask(self):
        state = self.state
        seat = state.turn_index
        me = state.players[seat]
        opp = state.players[1 - seat]
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
                len(me.hand) / 10.0,
                len(me.face_up) / 3.0,
                len(me.face_down) / 3.0,
                len(opp.hand) / 10.0,
                len(opp.face_down) / 3.0,
                len(state.pile) / 15.0,
                len(state.draw_pile) / 34.0,
                run / 4.0,
                1.0 if cons and cons.comparator is Comparator.GTE else 0.0,
                1.0 if cons and cons.comparator is Comparator.LTE and cons.value == 7 else 0.0,
                1.0 if cons and cons.comparator is Comparator.LTE and cons.value == 9 else 0.0,
                1.0 if len(state.draw_pile) == 0 else 0.0,
            ],
            dtype=np.float32,
        )
        obs = np.concatenate(
            [
                counts13(me.hand),
                counts13(me.face_up),
                counts13(opp.face_up),
                self.known[1 - seat],
                self.seen_gone / 4.0,
                top_onehot,
                scalars,
            ]
        )
        # Masque d'actions.
        mask = np.zeros(N_ACTIONS, dtype=bool)
        vals = playable_values(state, seat)
        for v in vals:
            i = v - 2
            copies = sum(1 for c in me.hand if c.value == v)
            if copies == len(me.hand):
                copies += sum(1 for c in me.face_up if c.value == v)
            dirs = (0, 1) if v == 7 else (0,)
            for d in dirs:
                mask[d * 26 + 13 + i] = True  # tout poser
                if copies > 1:
                    mask[d * 26 + i] = True  # une seule
        return obs, mask, seat

    def step(self, action):
        seat = self.state.turn_index
        value, mode_all, direction = decode_action(action)
        me = self.state.players[seat]
        copies = sum(1 for c in me.hand if c.value == value)
        if copies == len(me.hand):
            copies += sum(1 for c in me.face_up if c.value == value)
        count = copies if mode_all else 1
        self.step_raw(value, count, direction if value == 7 else None)

    def step_raw(self, value, count, direction):
        seat = self.state.turn_index
        pile_before = counts13(self.state.pile)
        events = play_cards(self.state, seat, value, count, direction)
        self._on_events(events, pile_before)
        self._auto_chase(seat)
        self.steps += 1
        self._to_decision()
