"""Bots de table : Facile (hasard), Normal (économe), Difficile (réseau PPO en numpy).

Un bot occupe un siège comme un joueur (Seat.bot = difficulté) mais n'a ni socket
ni profil en base. Il ne lit que ce qu'un joueur verrait à sa place : la vue de
son siège (room_view) et les événements publics diffusés à la table, dont il
tient une mémoire (cartes ramassées, cachées retournées). Jamais l'état brut.

Cadence : après chaque coup joué à la table, `schedule` programme l'action du
prochain bot avec un délai « humain » ; un jeton invalide les actions
programmées dès qu'un nouveau coup survient.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.games.base import AfterMove
from app.games.nine_to_one import botbrain
from app.games.nine_to_one.engine import (
    Comparator,
    GameError,
    GameStatus,
    add_player,
    chase_flip,
    chase_play,
    chase_value,
    flip_face_down,
    play_cards,
    set_ready,
    swap_cards,
)
from app.rooms.manager import Room, Seat, manager
from app.rooms.views import room_view

logger = logging.getLogger(__name__)

DIFFICULTIES = {"easy": "Facile", "normal": "Normal", "hard": "Difficile"}

FIRST_NAMES = [
    "Marcel",
    "Odette",
    "Gaston",
    "Simone",
    "Raymond",
    "Paulette",
    "Fernand",
    "Ginette",
    "Roger",
    "Huguette",
    "Lucien",
    "Josette",
    "Émile",
    "Colette",
    "Marius",
    "Yvette",
    "Léon",
    "Jeanne",
    "Albert",
    "Suzanne",
    "Robert",
    "Madeleine",
    "Jules",
    "Rose",
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

# Délais avant d'agir (secondes) : un tour, un enchaînement, la mise en place en lobby.
TURN_DELAY = (0.9, 1.7)
CHASE_DELAY = (0.4, 0.8)
LOBBY_DELAY = 0.8

# Score d'une valeur pour l'échange initial (Normal et Difficile) : les plus
# fortes vont face visible pour la fin de partie. Identique à ml/strategies.py.
SWAP_SCORE = {
    2: 15,
    10: 14,
    14: 13,
    13: 12,
    12: 11,
    11: 10,
    9: 9,
    7: 8,
    8: 6,
    6: 3,
    5: 2,
    4: 1.5,
    3: 1,
}

# Difficile : recherche déterminisée autour du réseau v2 (app/botbrain.py), calculée
# hors boucle d'événements dans un pool borné : au plus `bot_threads` réflexions à la
# fois, chacune plafonnée à `bot_time_budget` secondes (réglables dans .env).
HARD_SEARCH = True
HARD_N_SIMS = 300  # plafond de simulations ; la recherche s'arrête au budget de temps
HARD_HORIZON = 30
SEARCH_POOL = ThreadPoolExecutor(max_workers=settings.bot_threads, thread_name_prefix="bot")


# ---------------------------------------------------------------------------
# Sièges
# ---------------------------------------------------------------------------


def add_bot(room: Room, difficulty: str) -> Seat:
    """Assoit un bot en lobby (lève GameError si la table est pleine)."""
    # « Olga bot » : un prénom encore libre à cette table, sans numéro.
    taken = {s.pseudo for s in room.seats}
    free = [name for name in FIRST_NAMES if f"{name} bot" not in taken]
    pseudo = f"{random.choice(free)} bot" if free else f"Bot {len(room.seats) + 1}"
    add_player(room.state, pseudo)
    seat = Seat(
        player_id=uuid.uuid4(),
        pseudo=pseudo,
        avatar=f"{random.choice(AVATAR_ANIMALS)}-{random.randrange(6)}",
        bot=difficulty,
    )
    room.seats.append(seat)
    return seat


def log_game(room: Room) -> None:
    """Journalise une manche jouée contre au moins un bot (analyse hors ligne)."""
    if not settings.games_log_path or not any(s.bot for s in room.seats):
        return
    try:
        path = Path(settings.games_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "code": room.code,
            "seats": [{"pseudo": s.pseudo, "bot": s.bot} for s in room.seats],
            "ranks": [p.finish_rank for p in room.state.players],
            "initial_state": room.data.initial_state,
            "events": room.data.history,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("Journalisation de la partie %s impossible", room.code)


# ---------------------------------------------------------------------------
# Mémoire publique (ce qu'un observateur attentif sait des mains adverses)
# ---------------------------------------------------------------------------


def observe(room: Room, events: list[dict]) -> None:
    """À appeler après chaque coup, avec les événements diffusés à la table."""
    if not any(s.bot for s in room.seats):
        return
    n = len(room.state.players)
    started = any(e["type"] == "game_started" for e in events)
    if room.data.bot_memory is None or room.data.bot_memory.n != n or started:
        room.data.bot_memory = botbrain.Memory(n)
    room.data.bot_memory.on_events(events, botbrain.counts13(c.value for c in room.state.pile))


# ---------------------------------------------------------------------------
# Cerveaux : chacun décide depuis la vue de son siège
# ---------------------------------------------------------------------------


def _copies(me: dict, value: int) -> int:
    n = sum(1 for c in me["hand"] if c["value"] == value)
    if n == len(me["hand"]):
        n += sum(1 for c in me["face_up"] if c["value"] == value)
    return n


def _smart_swap(room: Room, seat: int) -> None:
    for _ in range(6):
        me = room_view(room, seat)["players"][seat]
        hand, up = me["hand"], me["face_up"]
        worst = min(range(len(up)), key=lambda i: SWAP_SCORE[up[i]["value"]])
        best = max(range(len(hand)), key=lambda i: SWAP_SCORE[hand[i]["value"]])
        if SWAP_SCORE[hand[best]["value"]] > SWAP_SCORE[up[worst]["value"]]:
            swap_cards(room.state, seat, best, worst)
        else:
            break


def _choose_easy(view: dict) -> tuple[int, int, Comparator | None]:
    """Un coup légal au hasard, une carte à la fois."""
    value = random.choice(view["playable_values"])
    direction = random.choice([Comparator.GTE, Comparator.LTE]) if value == 7 else None
    return value, 1, direction


def _choose_normal(view: dict) -> tuple[int, int, Comparator | None]:
    """Plus petite carte normale d'abord, toutes ses copies ; garde le 2 et le 10."""
    me = view["players"][view["your_seat"]]
    vals = view["playable_values"]
    normal = [v for v in vals if v not in (2, 10)]
    if normal:
        value = normal[0]
    elif 2 in vals:
        value = 2
    else:
        value = vals[0]
    direction = None
    if value == 7:
        hand = [c["value"] for c in me["hand"]]
        low = sum(1 for x in hand if x <= 7)
        direction = Comparator.LTE if low >= len(hand) - low else Comparator.GTE
    return value, _copies(me, value), direction


def _decode(view: dict, action: int) -> tuple[int, int, Comparator | None]:
    value, mode_all, direction = botbrain.decode_action(action)
    me = view["players"][view["your_seat"]]
    return value, _copies(me, value) if mode_all else 1, direction if value == 7 else None


async def _choose_hard(room: Room, view: dict) -> tuple[int, int, Comparator | None]:
    """Réseau v2 : glouton, ou recherche déterminisée (dans un thread, la
    boucle d'événements continue de servir les autres tables)."""
    seat = view["your_seat"]
    mem = room.data.bot_memory or botbrain.Memory(len(view["players"]))
    if HARD_SEARCH:
        action = await asyncio.get_running_loop().run_in_executor(
            SEARCH_POOL,
            botbrain.search_action,
            room.state,
            mem,
            seat,
            random.Random(),
            HARD_N_SIMS,
            HARD_HORIZON,
            settings.bot_time_budget,
        )
    else:
        action = botbrain.greedy_action(botbrain.snapshot_from_view(view), mem)
    return _decode(view, action)


CHASES = {"easy": False, "normal": True, "hard": True}
SWAPS = {"easy": False, "normal": True, "hard": True}


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
    for i, seat in enumerate(room.seats):
        if seat.bot and CHASES[seat.bot] and chase_value(state, i) is not None:
            return "chase", i, random.uniform(*CHASE_DELAY)
    turn = state.turn_index
    if room.seats[turn].bot:
        return "turn", turn, random.uniform(*TURN_DELAY)
    return None


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
            events = await _act(room, kind, seat)
        except GameError:
            logger.exception("Coup de bot impossible sur la table %s (%s)", room.code, kind)
            return
        await after_move(room, events)


async def _act(room: Room, kind: str, seat: int) -> list[dict]:
    state = room.state
    difficulty = room.seats[seat].bot
    if kind == "lobby":
        if SWAPS[difficulty]:
            _smart_swap(room, seat)
        return set_ready(state, seat)
    view = room_view(room, seat)
    me = view["players"][seat]
    if kind == "chase":
        if me["hand"]:
            return chase_play(state, seat, 1)
        return chase_flip(state, seat, random.randrange(me["face_down_count"]))
    if view["must_flip"]:
        return flip_face_down(state, seat, random.randrange(me["face_down_count"]))
    if difficulty == "hard":
        value, count, direction = await _choose_hard(room, view)
    elif difficulty == "normal":
        value, count, direction = _choose_normal(view)
    else:
        value, count, direction = _choose_easy(view)
    return play_cards(state, seat, value, count, direction)
