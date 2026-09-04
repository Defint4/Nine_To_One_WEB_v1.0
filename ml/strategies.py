"""Laboratoire de stratégies Nine to One : politiques jouées sur le vrai moteur,
tournois à N parties, mesure des taux de victoire (2 joueurs : gagnant/perdant).

Information honnête : une politique ne lit que sa main, le tas, les tailles,
les cartes visibles de tous, et une mémoire construite depuis les événements
publics (poses, ramassages, cartes retournées).
"""

import random
import sys
from collections import defaultdict

sys.path.insert(0, "/home/defint/projects/nine_to_one/backend")

from app.engine import (  # noqa: E402
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
from app.engine.state import Comparator  # noqa: E402

# Score d'une valeur pour la phase d'échange (plus haut = à mettre face visible
# pour la fin de partie). Les 2 et 10 sont les jokers, l'As la plus forte.
SWAP_SCORE = {2: 15, 10: 14, 14: 13, 13: 12, 12: 11, 11: 10, 9: 9, 7: 8, 8: 6, 6: 3, 5: 2, 4: 1.5, 3: 1}


class Memory:
    """Ce qu'un observateur attentif sait des mains adverses (info publique)."""

    def __init__(self, n):
        self.known = [[] for _ in range(n)]  # valeurs connues dans chaque main

    def on_events(self, events, pile_values_before):
        for e in events:
            t = e["type"]
            if t == "cards_played":
                for cd in e["cards"]:
                    self._forget(e["player"], cd["value"])
            elif t == "pile_picked_up":
                self.known[e["player"]].extend(pile_values_before)
            elif t == "card_flipped":
                self.known[e["player"]].append(e["card"]["value"])

    def _forget(self, seat, value):
        if value in self.known[seat]:
            self.known[seat].remove(value)


# ---------------------------------------------------------------------------
# Politiques
# ---------------------------------------------------------------------------


class Base:
    name = "base"
    chases = False

    def swap_setup(self, state, seat, rng):
        pass

    def flip_index(self, state, seat, rng):
        return rng.randrange(len(state.players[seat].face_down))

    def wants_chase(self, state, seat, value, rng):
        return self.chases

    def direction(self, state, seat, mem, rng):
        return rng.choice([Comparator.GTE, Comparator.LTE])

    def counts_for(self, state, seat, value):
        player = state.players[seat]
        n = sum(1 for c in player.hand if c.value == value)
        if n == len(player.hand):
            n += sum(1 for c in player.face_up if c.value == value)
        return n


class Rand(Base):
    """Joue au hasard parmi les coups légaux."""

    name = "hasard"

    def choose(self, state, seat, mem, rng):
        vals = sorted(playable_values(state, seat))
        v = rng.choice(vals)
        count = rng.randint(1, self.counts_for(state, seat, v))
        d = self.direction(state, seat, mem, rng) if v == 7 else None
        return v, count, d


class GreedyLow(Base):
    """Toujours la plus petite carte jouable, toutes copies. Enchaîne."""

    name = "plus-petite"
    chases = True

    def choose(self, state, seat, mem, rng):
        vals = sorted(playable_values(state, seat))
        v = vals[0]
        d = self.direction(state, seat, mem, rng) if v == 7 else None
        return v, self.counts_for(state, seat, v), d

    def direction(self, state, seat, mem, rng):
        hand = [c.value for c in state.players[seat].hand]
        low = sum(1 for x in hand if x <= 7)
        return Comparator.LTE if low >= len(hand) - low else Comparator.GTE


class SaveSpecials(GreedyLow):
    """Plus petite carte NORMALE d'abord ; garde 2 et 10 pour se sortir d'un
    blocage. Échange initial : met ses cartes les plus fortes face visible."""

    name = "econome"

    def swap_setup(self, state, seat, rng):
        player = state.players[seat]
        for _ in range(6):
            worst_up = min(range(len(player.face_up)), key=lambda i: SWAP_SCORE[player.face_up[i].value])
            best_hand = max(range(len(player.hand)), key=lambda i: SWAP_SCORE[player.hand[i].value])
            if SWAP_SCORE[player.hand[best_hand].value] > SWAP_SCORE[player.face_up[worst_up].value]:
                swap_cards(state, seat, best_hand, worst_up)
            else:
                break

    def choose(self, state, seat, mem, rng):
        vals = sorted(playable_values(state, seat))
        normal = [v for v in vals if v not in (2, 10)]
        if normal:
            v = normal[0]
        elif 2 in vals:
            v = 2  # garde le 10 (coupe) pour plus tard
        else:
            v = vals[0]
        d = self.direction(state, seat, mem, rng) if v == 7 else None
        return v, self.counts_for(state, seat, v), d


class Punisher(SaveSpecials):
    """Stratégie complète : compte les cartes, punit les mains faibles connues,
    choisit les directions du 7 contre l'adversaire, coupe au bon moment,
    vise le carré, gère la fin de pioche."""

    name = "punisseur"

    def choose(self, state, seat, mem, rng):
        vals = sorted(playable_values(state, seat))
        player = state.players[seat]
        pile = state.pile
        top_run = 0
        if pile:
            top_v = pile[-1].value
            top_run = 1
            for c in reversed(pile[:-1]):
                if c.value == top_v:
                    top_run += 1
                else:
                    break

        opp = self._next_opponent(state, seat)
        known = list(mem.known[opp]) if opp is not None else []
        opp_hand_count = len(state.players[opp].hand) if opp is not None else 0
        known_ratio = len(known) / opp_hand_count if opp_hand_count else 0

        endgame = len(state.draw_pile) == 0
        best, best_score = None, -1e9
        for v in vals:
            count = self.counts_for(state, seat, v)
            score = 0.0
            # Se défausser bas d'abord ; en fin de pioche c'est encore plus vrai.
            score -= v * (1.6 if endgame else 1.0)
            # Les multiples vident la main et menacent le carré.
            score += count * 2.2
            # Compléter un carré : coupe + on rejoue.
            if pile and v == pile[-1].value and top_run + count >= 4:
                score += 14
            # Punition : l'adversaire connu incapable de suivre => il ramasse tout.
            if known and known_ratio >= 0.6 and v != 2 and v != 10:
                beats = self._count_beating(known, v)
                if beats == 0:
                    score += 7 + 0.4 * len(pile)
            # Un 9 qui force "9 ou moins" contre une main connue haute.
            if v == 9 and known and known_ratio >= 0.6:
                if all(x > 9 or x == 10 for x in known):
                    score += 8
            # Économiser les jokers : 2 en dernier recours, 10 si le tas est gros
            # ou si tout le reste est haut.
            if v == 2:
                score -= 12
            if v == 10:
                score -= 22
                score += min(len(pile), 10) * 1.5  # ne coupe spontanément qu'un très gros tas
            best_of = (score, v, count)
            if score > best_score:
                best_score, best = score, (v, count)
        v, count = best
        # Ne pas gaspiller un multiple entier si ça casse la menace de carré ?
        d = self.direction(state, seat, mem, rng) if v == 7 else None
        return v, count, d

    def direction(self, state, seat, mem, rng):
        hand = [c.value for c in state.players[seat].hand if c.value != 7]
        opp = self._next_opponent(state, seat)
        known = mem.known[opp] if opp is not None else []
        my_low = sum(1 for x in hand if x <= 7)
        my_high = len(hand) - my_low
        opp_low = sum(1 for x in known if x <= 7 or x == 2)
        opp_high = sum(1 for x in known if x > 7)
        # Direction qui m'arrange et gêne l'adversaire connu.
        score_le = my_low - opp_low * 0.8
        score_ge = my_high - opp_high * 0.8
        return Comparator.LTE if score_le >= score_ge else Comparator.GTE

    @staticmethod
    def _count_beating(known, v):
        # Cartes connues capables de suivre une valeur v : >= v, ou 2 (toujours),
        # ou 10 (sauf contrainte basse, approximé ici).
        return sum(1 for x in known if x >= v or x == 2 or x == 10)

    @staticmethod
    def _next_opponent(state, seat):
        n = len(state.players)
        for step in range(1, n + 1):
            cand = (seat + step) % n
            if cand != seat and not state.players[cand].finished:
                return cand
        return None


# ---------------------------------------------------------------------------
# Tournoi
# ---------------------------------------------------------------------------


def play_game(policies, seed):
    rng = random.Random(seed)
    state = create_game("P0", seed=seed)
    for i in range(1, len(policies)):
        add_player(state, f"P{i}")
    for i, pol in enumerate(policies):
        pol.swap_setup(state, i, rng)
    for i in range(len(policies)):
        set_ready(state, i)
    mem = Memory(len(policies))
    steps = 0
    while state.status is GameStatus.PLAYING and steps < 4000:
        steps += 1
        seat = state.turn_index
        pol = policies[seat]
        pile_vals = [c.value for c in state.pile]
        if not state.players[seat].hand:
            events = flip_face_down(state, seat, pol.flip_index(state, seat, rng))
        else:
            v, count, d = pol.choose(state, seat, mem, rng)
            events = play_cards(state, seat, v, count, d)
        mem.on_events(events, pile_vals)
        # Fenêtre de « bonne pioche » pour le poseur.
        guard = 0
        while state.status is GameStatus.PLAYING and guard < 8:
            guard += 1
            cv = chase_value(state, seat)
            if cv is None or not pol.wants_chase(state, seat, cv, rng):
                break
            pile_vals = [c.value for c in state.pile]
            p = state.players[seat]
            if p.hand:
                events = chase_play(state, seat, 1)
            elif p.face_down:
                events = chase_flip(state, seat, rng.randrange(len(p.face_down)))
            else:
                break
            mem.on_events(events, pile_vals)
    if state.status is not GameStatus.FINISHED:
        return None, steps
    return [p.finish_rank for p in state.players], steps


def duel(pa, pb, games=600, seed0=0):
    """Duel 2 joueurs, sièges alternés. Renvoie (taux de victoire de A, nuls)."""
    wins_a = draws = 0
    lengths = []
    for g in range(games):
        order = [pa, pb] if g % 2 == 0 else [pb, pa]
        ranks, steps = play_game(order, seed0 + g)
        lengths.append(steps)
        if ranks is None:
            draws += 1
            continue
        winner = ranks.index(1)
        first_is_a = g % 2 == 0
        if (winner == 0) == first_is_a:
            wins_a += 1
    decided = games - draws
    return wins_a / decided if decided else 0.5, draws, sum(lengths) / len(lengths)


class NoChase(SaveSpecials):
    name = "econome-sans-enchaine"
    chases = False


class OneAtATime(SaveSpecials):
    name = "econome-sans-multiples"

    def counts_for(self, state, seat, value):
        return 1


class RandomDir(SaveSpecials):
    name = "econome-direction-hasard"

    def direction(self, state, seat, mem, rng):
        return rng.choice([Comparator.GTE, Comparator.LTE])




class MonteCarlo(SaveSpecials):
    """Difficile : pour chaque coup candidat, déterminise les cartes cachées et
    joue la partie mentalement (politique économe pour tous) ; choisit le coup
    au meilleur taux de victoire simulé."""

    name = "monte-carlo"

    def __init__(self, rollouts=20, horizon=300):
        self.rollouts = rollouts
        self.horizon = horizon
        self.inner = SaveSpecials()

    def choose(self, state, seat, mem, rng):
        vals = sorted(playable_values(state, seat))
        candidates = []
        for v in vals:
            count = self.counts_for(state, seat, v)
            if v == 7:
                candidates.append((v, count, Comparator.GTE))
                candidates.append((v, count, Comparator.LTE))
            else:
                candidates.append((v, count, None))
            if count > 1:
                candidates.append((v, 1, Comparator.GTE if v == 7 else None))
        if len(candidates) == 1:
            return candidates[0]
        best, best_score = candidates[0], -1.0
        for cand in candidates:
            score = 0.0
            for r in range(self.rollouts):
                score += self._rollout(state, seat, cand, rng)
            score /= self.rollouts
            if score > best_score:
                best_score, best = score, cand
        return best

    def _rollout(self, state, seat, move, rng):
        from app.engine import GameState
        sim = GameState.from_dict(state.to_dict())
        self._scramble_hidden(sim, seat, rng)
        try:
            play_cards(sim, seat, move[0], move[1], move[2])
        except Exception:
            return 0.0
        steps = 0
        while sim.status is GameStatus.PLAYING and steps < self.horizon:
            steps += 1
            s = sim.turn_index
            if not sim.players[s].hand:
                flip_face_down(sim, s, rng.randrange(len(sim.players[s].face_down)))
            else:
                v, c, d = self.inner.choose(sim, s, None, rng)
                play_cards(sim, s, v, c, d)
        if sim.status is not GameStatus.FINISHED:
            return 0.5
        me = sim.players[seat]
        loser_rank = len(sim.players)
        if me.finish_rank == 1:
            return 1.0
        return 0.0 if me.finish_rank == loser_rank else 0.4

    def _scramble_hidden(self, sim, seat, rng):
        """Cartes cachées pour moi : mains adverses, cachées de tous, pioche."""
        hidden = []
        for i, p in enumerate(sim.players):
            if i != seat:
                hidden.extend(p.hand)
            hidden.extend(p.face_down)
        hidden.extend(sim.draw_pile)
        rng.shuffle(hidden)
        it = iter(hidden)
        for i, p in enumerate(sim.players):
            if i != seat:
                p.hand = sorted([next(it) for _ in p.hand], key=lambda c: (c.value, c.suit.value))
            p.face_down = [next(it) for _ in p.face_down]
        sim.draw_pile = [next(it) for _ in sim.draw_pile]


if __name__ == "__main__":
    random.seed(1)
    matchups = [
        ("monte-carlo vs econome", MonteCarlo(), SaveSpecials()),
    ]
    for label, a, b in matchups:
        rate, draws, avg_len = duel(a, b, games=150)
        print(f"{label:42s} winrate={rate:5.1%}  nuls={draws:3d}  coups moyens={avg_len:5.0f}")
