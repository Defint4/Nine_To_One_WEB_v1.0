"""Bots du Goulag : Facile (hasard) et Normal (heuristique).

Un bot occupe un siège comme un joueur (Seat.bot = difficulté) mais n'a ni socket ni
profil. Il décide depuis la vue de son siège (room_view), jamais depuis l'état brut :
il ne voit donc ni les charges ni la pioche, comme un humain.

Cadence : après chaque coup, `schedule` programme l'action du prochain bot avec un
délai « humain » ; room.bot_token invalide les actions programmées dès qu'un
nouveau coup survient.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid

from app.games.base import AfterMove
from app.games.goulag.engine import (
    Action,
    GameError,
    GameStatus,
    Phase,
    Suit,
    add_player,
    announce,
    choose_suit,
    choose_target,
    set_ready,
)
from app.rooms.manager import Room, Seat, manager
from app.rooms.views import room_view

logger = logging.getLogger(__name__)

DIFFICULTIES = {"easy": "Facile", "normal": "Normal"}

FIRST_NAMES = [
    "Igor",
    "Olga",
    "Dimitri",
    "Natacha",
    "Boris",
    "Svetlana",
    "Ivan",
    "Tatiana",
    "Sacha",
    "Irina",
    "Nikolaï",
    "Ludmila",
    "Piotr",
    "Anya",
    "Youri",
    "Katia",
]
AVATAR_ANIMALS = [
    "renard",
    "panda",
    "grenouille",
    "chat",
    "lion",
    "pieuvre",
    "koala",
    "loup",
    "poussin",
    "tigre",
    "singe",
    "licorne",
    "requin",
    "hibou",
    "dino",
    "axolotl",
]

# Délais avant d'agir (secondes) : annoncer, cibler (après avoir « regardé » la carte),
# choisir sa couleur, se mettre prêt en lobby.
ANNOUNCE_DELAY = (1.0, 1.8)
TARGET_DELAY = (0.9, 1.5)
SUIT_DELAY = (1.2, 2.0)
LOBBY_DELAY = 0.8


def add_bot(room: Room, difficulty: str) -> Seat:
    """Assoit un bot en lobby (lève GameError si la table est pleine)."""
    n = 1
    while any(s.pseudo.endswith(f"_bot_{n}") for s in room.seats):
        n += 1
    pseudo = f"{random.choice(FIRST_NAMES)}_bot_{n}"
    add_player(room.state, pseudo)
    seat = Seat(
        player_id=uuid.uuid4(),
        pseudo=pseudo,
        avatar=f"{random.choice(AVATAR_ANIMALS)}-{random.randrange(6)}",
        bot=difficulty,
    )
    room.seats.append(seat)
    return seat


# ---------------------------------------------------------------------------
# Décisions (depuis la vue du siège)
# ---------------------------------------------------------------------------


def _opponents(view: dict) -> list[int]:
    me = view["your_seat"]
    return [p["seat"] for p in view["players"] if p["alive"] and p["seat"] != me]


def _choose_action(view: dict, difficulty: str) -> Action:
    me = view["players"][view["your_seat"]]
    options = [Action.ATTACK, Action.DEFEND] + ([Action.CHARGE] if view["can_charge"] else [])
    if difficulty == "easy":
        return random.choice(options)
    # Normal : une défense faible se répare ; sinon on charge un peu, puis on frappe.
    defense = me["defense"]["value"] if me["defense"] else 0
    if defense <= 4 and random.random() < 0.6:
        return Action.DEFEND
    if view["can_charge"] and me["charges"] == 0 and random.random() < 0.45:
        return Action.CHARGE
    if view["can_charge"] and me["charges"] == 1 and random.random() < 0.25:
        return Action.CHARGE
    return Action.ATTACK


def _choose_target(view: dict, difficulty: str) -> int:
    """La cible se choisit sans connaître la carte (sauf œil de faucon : `peek`)."""
    me_seat = view["your_seat"]
    me = view["players"][me_seat]
    others = _opponents(view)
    known = view["peek"]["value"] if view["peek"] else None
    if view["pending_action"] == "defend":
        if difficulty == "easy":
            return random.choice([me_seat, *others])
        mine = me["defense"]["value"] if me["defense"] else 0
        if known is not None:
            return me_seat if known > mine else _sturdiest(view, others)
        # Carte inconnue (7 en moyenne) : on se répare si on est fragile, sinon on
        # tente d'affaiblir la défense la plus solide en face.
        return me_seat if mine < 8 else _sturdiest(view, others)
    if difficulty == "easy":
        return random.choice(others)
    # Attaque : carte inconnue estimée à 7, chaque charge (jamais vue) à 7 aussi.
    expected = (known if known is not None else 7) + 7 * me["charges"]

    def damage(seat: int) -> int:
        return max(0, expected - view["players"][seat]["defense"]["value"])

    killable = [s for s in others if 0 < view["players"][s]["life_total"] <= damage(s)]
    if killable:
        return min(killable, key=lambda s: view["players"][s]["life_total"])
    return max(others, key=lambda s: (damage(s), -view["players"][s]["life_total"]))


def _sturdiest(view: dict, seats: list[int]) -> int:
    return max(seats, key=lambda s: view["players"][s]["defense"]["value"])


def _choose_suit(view: dict, difficulty: str) -> Suit:
    if difficulty == "easy":
        return random.choice(list(Suit))
    # La couleur la moins visible sur la table est la plus présente dans la pioche.
    seen: dict[str, int] = {s.value: 0 for s in Suit}
    for p in view["players"]:
        for c in p["lives"]:
            seen[c["suit"]] += 1
        if p["defense"]:
            seen[p["defense"]["suit"]] += 1
    if view["discard_top"]:
        seen[view["discard_top"]["suit"]] += 1
    return Suit(min(seen, key=lambda s: seen[s]))


# ---------------------------------------------------------------------------
# Cadencement
# ---------------------------------------------------------------------------


def _plan(room: Room) -> tuple[str, int, float] | None:
    """(action, siège, délai) du prochain bot qui doit agir, ou None."""
    state = room.state
    if state.status is GameStatus.LOBBY:
        for i, seat in enumerate(room.seats):
            if seat.bot and not state.players[i].ready:
                return "lobby", i, LOBBY_DELAY
        return None
    if state.status is not GameStatus.PLAYING:
        return None
    if state.phase is Phase.REVIVAL:
        seat = state.reviving
        if seat is not None and room.seats[seat].bot:
            return "suit", seat, random.uniform(*SUIT_DELAY)
        return None
    turn = state.turn_index
    if not room.seats[turn].bot:
        return None
    if state.phase is Phase.TARGET:
        return "target", turn, random.uniform(*TARGET_DELAY)
    return "announce", turn, random.uniform(*ANNOUNCE_DELAY)


def schedule(room: Room, after_move: AfterMove) -> None:
    """À appeler sous room.lock après tout changement d'état de la table."""
    room.bot_token += 1
    plan = _plan(room)
    if plan is None:
        return
    asyncio.get_running_loop().create_task(_run(room, room.bot_token, plan, after_move))


async def _run(room: Room, token: int, plan: tuple[str, int, float], after_move: AfterMove) -> None:
    kind, seat, delay = plan
    await asyncio.sleep(delay)
    async with room.lock:
        if manager.get(room.code) is not room or room.bot_token != token:
            return
        try:
            events = _act(room, kind, seat)
        except GameError:
            logger.exception("Coup de bot impossible sur la table %s (%s)", room.code, kind)
            return
        await after_move(room, events)


def _act(room: Room, kind: str, seat: int) -> list[dict]:
    state = room.state
    difficulty = room.seats[seat].bot or "easy"
    if kind == "lobby":
        return set_ready(state, seat)
    view = room_view(room, seat)
    if kind == "suit":
        return choose_suit(state, seat, _choose_suit(view, difficulty))
    if kind == "target":
        return choose_target(state, seat, _choose_target(view, difficulty))
    return announce(state, seat, _choose_action(view, difficulty))
