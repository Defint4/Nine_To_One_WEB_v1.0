"""REST (créer / rejoindre / lister) + WebSocket temps réel d'une partie.

Flux : POST /api/rooms ou /api/rooms/{code}/join (authentifié) pour s'asseoir,
puis WS /api/rooms/{code}/ws?token=... pour jouer. Le serveur est seul juge des
règles : le client n'envoie que des intentions, jamais d'état.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from app import bots
from app.core.database import async_session_maker
from app.core.rate_limit import limiter
from app.core.security import decode_player_token
from app.engine import (
    Comparator,
    GameError,
    GameStatus,
    add_player,
    chase_flip,
    chase_play,
    create_game,
    flip_face_down,
    play_cards,
    playable_values,
    remove_player,
    set_ready,
    swap_cards,
)
from app.players import service as players_service
from app.players.dependencies import get_current_player
from app.players.models import Player
from app.rooms.manager import Room, Seat, manager
from app.rooms.schemas import RoomOut, open_room_summary
from app.rooms.views import room_view

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

CHAT_MAX_LENGTH = 200
EMOTE_PATTERN = re.compile(r"^[a-z0-9_\-]{1,30}$")
TURN_SECONDS_CHOICES = {0, 30, 60}


# ---------------------------------------------------------------------------
# REST : créer, rejoindre, lister
# ---------------------------------------------------------------------------


@router.post("", response_model=RoomOut)
@limiter.limit("10/minute")
async def create_room(request: Request, player: Player = Depends(get_current_player)) -> RoomOut:
    state = create_game(player.pseudo)
    room = manager.create(
        state, Seat(player_id=player.id, pseudo=player.pseudo, avatar=player.avatar)
    )
    return RoomOut(code=room.code)


@router.post("/{code}/join", response_model=RoomOut)
@limiter.limit("30/minute")
async def join_room(
    request: Request, code: str, player: Player = Depends(get_current_player)
) -> RoomOut:
    room = manager.get(code)
    if room is None:
        raise HTTPException(status_code=404, detail="Partie introuvable.")
    async with room.lock:
        if room.seat_of(player.id) is not None:
            return RoomOut(code=room.code)  # déjà assis : reconnexion
        if room.state.status is not GameStatus.LOBBY:
            raise HTTPException(status_code=403, detail="La partie a déjà commencé.")
        try:
            add_player(room.state, player.pseudo)
        except GameError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        room.seats.append(Seat(player_id=player.id, pseudo=player.pseudo, avatar=player.avatar))
        room.touch()
        await _broadcast_state(room, [{"type": "player_joined", "pseudo": player.pseudo}])
    return RoomOut(code=room.code)


@router.get("")
async def list_open_rooms() -> list[dict]:
    return [open_room_summary(room) for room in manager.open_rooms()]


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/{code}/ws")
async def room_ws(websocket: WebSocket, code: str) -> None:
    try:
        player_id = decode_player_token(websocket.query_params.get("token") or "")
    except jwt.InvalidTokenError:
        await websocket.close(code=4401)
        return
    room = manager.get(code)
    if room is None:
        await websocket.close(code=4404)
        return
    if room.seat_of(player_id) is None:
        await websocket.close(code=4403)  # s'asseoir d'abord via REST join
        return

    await websocket.accept()
    async with room.lock:
        seat_index = room.seat_of(player_id)
        if seat_index is None:
            await websocket.close(code=4403)
            return
        seat = room.seats[seat_index]
        if seat.socket is not None:
            # Nouvelle connexion (autre onglet / retour d'app) : elle remplace l'ancienne.
            try:
                await seat.socket.close(code=4000)
            except Exception:
                pass
        seat.socket = websocket
        room.touch()
        await _send_view(room, seat_index)
        await _broadcast_state(room, [])

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_message(room, player_id, websocket, message)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass  # socket déjà fermé (remplacé par une connexion plus récente)
    finally:
        await _handle_disconnect(room, player_id, websocket)


LOBBY_SEAT_GRACE_SECONDS = 10


async def _handle_disconnect(room: Room, player_id: uuid.UUID, websocket: WebSocket) -> None:
    async with room.lock:
        seat_index = room.seat_of(player_id)
        if seat_index is None or room.seats[seat_index].socket is not websocket:
            return  # déjà remplacé par une connexion plus récente
        room.seats[seat_index].socket = None
        room.touch()
        if room.state.status is GameStatus.LOBBY:
            # En lobby, le siège n'est libéré qu'après un délai de grâce : un refresh
            # de page ne doit pas éjecter le joueur. En partie, le siège attend
            # la reconnexion sans limite.
            asyncio.get_running_loop().create_task(_expire_lobby_seat(room, player_id))
        await _broadcast_state(room, [])


async def _expire_lobby_seat(room: Room, player_id: uuid.UUID) -> None:
    await asyncio.sleep(LOBBY_SEAT_GRACE_SECONDS)
    async with room.lock:
        if manager.get(room.code) is not room or room.state.status is not GameStatus.LOBBY:
            return
        seat_index = room.seat_of(player_id)
        if seat_index is None or room.seats[seat_index].socket is not None:
            return  # parti autrement, ou revenu entre-temps
        remove_player(room.state, seat_index)
        room.seats.pop(seat_index)
        if room.human_count() == 0:
            manager.delete(room.code)
            return
        bots.humans_first(room)
        await _broadcast_state(room, [{"type": "player_left", "seat": seat_index}])


async def _handle_message(
    room: Room, player_id: uuid.UUID, websocket: WebSocket, message: dict
) -> None:
    if not isinstance(message, dict):
        return
    action = message.get("action")
    async with room.lock:
        seat_index = room.seat_of(player_id)
        if seat_index is None:
            return
        try:
            if action == "swap":
                swap_cards(
                    room.state,
                    seat_index,
                    int(message["hand_index"]),
                    int(message["face_up_index"]),
                )
                await _after_move(room, [])
            elif action == "ready":
                events = set_ready(room.state, seat_index, bool(message.get("ready", True)))
                await _after_move(room, events)
            elif action == "play":
                direction = message.get("direction")
                events = play_cards(
                    room.state,
                    seat_index,
                    int(message["value"]),
                    count=int(message.get("count", 1)),
                    direction=Comparator(direction) if direction else None,
                )
                await _after_move(room, events)
            elif action == "flip":
                events = flip_face_down(room.state, seat_index, int(message["index"]))
                await _after_move(room, events)
            elif action == "chase":
                events = chase_play(room.state, seat_index, int(message.get("count", 1)))
                await _after_move(room, events)
            elif action == "chase_flip":
                events = chase_flip(room.state, seat_index, int(message["index"]))
                await _after_move(room, events)
            elif action == "sync":
                # Retour d'arrière-plan sur mobile : le client redemande sa vue.
                await _send_view(room, seat_index)
            elif action == "leave":
                # Départ volontaire : en lobby le siège est libéré tout de suite
                # (pas de délai de grâce) ; en partie il attend un éventuel retour.
                if room.state.status is GameStatus.LOBBY:
                    room.seats[seat_index].socket = None
                    remove_player(room.state, seat_index)
                    room.seats.pop(seat_index)
                    if room.human_count() == 0:
                        manager.delete(room.code)
                    else:
                        bots.humans_first(room)
                        await _broadcast_state(room, [{"type": "player_left", "seat": seat_index}])
                await websocket.close(code=1000)
            elif action == "add_bot":
                # Seul le créateur (siège 0) gère les bots, uniquement en lobby.
                difficulty = str(message.get("difficulty", ""))
                if room.state.status is not GameStatus.LOBBY:
                    await _send_error(websocket, "La partie a déjà commencé.")
                elif seat_index != 0:
                    await _send_error(websocket, "Seul le créateur de la table ajoute des bots.")
                elif difficulty not in bots.DIFFICULTIES:
                    await _send_error(websocket, "Difficulté inconnue.")
                else:
                    seat = bots.add_bot(room, difficulty)
                    await _after_move(room, [{"type": "player_joined", "pseudo": seat.pseudo}])
            elif action == "remove_bot":
                target = int(message["seat"])
                if room.state.status is not GameStatus.LOBBY:
                    await _send_error(websocket, "La partie a déjà commencé.")
                elif seat_index != 0:
                    await _send_error(websocket, "Seul le créateur de la table retire des bots.")
                elif not (0 <= target < len(room.seats)) or room.seats[target].bot is None:
                    await _send_error(websocket, "Ce siège n'est pas un bot.")
                else:
                    remove_player(room.state, target)
                    room.seats.pop(target)
                    await _after_move(room, [{"type": "player_left", "seat": target}])
            elif action == "chat":
                text = str(message.get("text", "")).strip()[:CHAT_MAX_LENGTH]
                if text:
                    entry = {"type": "chat", "seat": seat_index, "text": text}
                    room.add_chat(entry)
                    room.touch()
                    await _broadcast(room, entry)
            elif action == "emote":
                emote = str(message.get("emote", ""))
                target = message.get("target")
                if target is not None:
                    target = int(target)
                    if not (0 <= target < len(room.seats)):
                        target = None
                if EMOTE_PATTERN.fullmatch(emote):
                    room.touch()
                    await _broadcast(
                        room,
                        {"type": "emote", "seat": seat_index, "emote": emote, "target": target},
                    )
            elif action == "config":
                # Seul le créateur (siège 0) règle la table, et uniquement en lobby.
                seconds = int(message.get("turn_seconds", 0))
                if room.state.status is not GameStatus.LOBBY:
                    await _send_error(websocket, "La partie a déjà commencé.")
                elif seat_index != 0:
                    await _send_error(websocket, "Seul le créateur de la table règle le temps.")
                elif seconds not in TURN_SECONDS_CHOICES:
                    await _send_error(websocket, "Durée de tour invalide.")
                else:
                    room.turn_seconds = seconds
                    room.touch()
                    await _broadcast_state(room, [])
            elif action == "rematch":
                await _handle_rematch(room, seat_index, websocket)
            else:
                await _send_error(websocket, "Action inconnue.")
        except GameError as exc:
            await _send_error(websocket, str(exc))
        except (KeyError, TypeError, ValueError):
            await _send_error(websocket, "Message mal formé.")


async def _after_move(room: Room, events: list[dict]) -> None:
    room.touch()
    for event in events:
        if event["type"] == "cards_played":
            room.moves += 1
        elif event["type"] == "pile_picked_up":
            seat = event["player"]
            room.pickups[seat] = room.pickups.get(seat, 0) + 1
        elif event["type"] == "game_started":
            room.initial_state = room.state.to_dict()
            room.history = []
    room.history.extend(events)
    if any(e["type"] == "game_over" for e in events) and not room.stats_recorded:
        room.stats_recorded = True
        await _record_stats(room)
        bots.log_game(room)
    _schedule_turn_timer(room)
    await _broadcast_state(room, events)
    bots.observe(room, events)
    bots.schedule(room, _after_move)


def _schedule_turn_timer(room: Room) -> None:
    """(Re)programme l'échéance du tour courant ; invalide le timer précédent."""
    room.turn_token += 1
    if room.state.status is not GameStatus.PLAYING or room.turn_seconds <= 0:
        room.turn_deadline = None
        return
    room.turn_deadline = time.monotonic() + room.turn_seconds
    asyncio.get_running_loop().create_task(_turn_timeout(room, room.turn_token, room.turn_seconds))


async def _turn_timeout(room: Room, token: int, delay: float) -> None:
    await asyncio.sleep(delay)
    async with room.lock:
        if (
            manager.get(room.code) is not room
            or room.turn_token != token
            or room.state.status is not GameStatus.PLAYING
        ):
            return
        seat = room.state.turn_index
        try:
            events = _auto_play(room, seat)
        except GameError:
            logger.exception("Coup automatique impossible sur la table %s", room.code)
            return
        await _after_move(room, [{"type": "auto_played", "player": seat}, *events])


def _auto_play(room: Room, seat: int) -> list[dict]:
    """Temps écoulé : le serveur joue le coup le plus simple pour le joueur."""
    state = room.state
    player = state.players[seat]
    if not player.hand:
        return flip_face_down(state, seat, random.randrange(len(player.face_down)))
    value = min(playable_values(state, seat))
    direction = Comparator.GTE if value == 7 else None
    return play_cards(state, seat, value, count=1, direction=direction)


async def _handle_rematch(room: Room, seat_index: int, websocket: WebSocket) -> None:
    """Crée une table de revanche avec les joueurs encore connectés et les y emmène."""
    if room.state.status is not GameStatus.FINISHED:
        await _send_error(websocket, "La revanche se lance en fin de partie.")
        return
    if room.rematch_code and manager.get(room.rematch_code):
        await _broadcast(room, {"type": "rematch", "code": room.rematch_code})
        return
    # Les humains connectés d'abord (le siège 0 doit rester un humain), puis les bots.
    connected = [s for s in room.seats if s.socket is not None] + [s for s in room.seats if s.bot]
    if len(connected) < 2:
        await _send_error(websocket, "Il faut au moins deux joueurs connectés pour une revanche.")
        return
    state = create_game(connected[0].pseudo)
    new_room = manager.create(
        state,
        Seat(
            player_id=connected[0].player_id, pseudo=connected[0].pseudo, avatar=connected[0].avatar
        ),
    )
    for seat in connected[1:]:
        add_player(state, seat.pseudo)
        new_room.seats.append(
            Seat(player_id=seat.player_id, pseudo=seat.pseudo, avatar=seat.avatar, bot=seat.bot)
        )
    new_room.turn_seconds = room.turn_seconds
    room.rematch_code = new_room.code
    room.touch()
    await _broadcast(room, {"type": "rematch", "code": new_room.code})
    bots.schedule(new_room, _after_move)


async def _record_stats(room: Room) -> None:
    winner_seat = next((i for i, p in enumerate(room.state.players) if p.finish_rank == 1), None)
    loser_seat = max(
        range(len(room.state.players)), key=lambda i: room.state.players[i].finish_rank or 0
    )
    humans = [seat.player_id for seat in room.seats if seat.bot is None]
    if winner_seat is None or not humans:
        return
    try:
        async with async_session_maker() as db:
            # Seuls les humains ont un profil ; un bot gagnant ou perdant n'apparaît nulle part.
            await players_service.record_game_results(
                db,
                humans,
                winner_id=room.seats[winner_seat].player_id,
                loser_id=room.seats[loser_seat].player_id,
            )
    except Exception:
        logger.exception("Échec de l'enregistrement des stats de la partie %s", room.code)


async def _send_view(room: Room, seat_index: int) -> None:
    socket = room.seats[seat_index].socket
    if socket is None:
        return
    try:
        await socket.send_json(
            {"type": "state", "events": [], "view": room_view(room, seat_index), "chat": room.chat}
        )
    except Exception:
        pass


async def _broadcast_state(room: Room, events: list[dict]) -> None:
    for i, seat in enumerate(list(room.seats)):
        if seat.socket is None:
            continue
        try:
            await seat.socket.send_json(
                {"type": "state", "events": events, "view": room_view(room, i)}
            )
        except Exception:
            pass


async def _broadcast(room: Room, message: dict) -> None:
    for seat in list(room.seats):
        if seat.socket is None:
            continue
        try:
            await seat.socket.send_json(message)
        except Exception:
            pass


async def _send_error(websocket: WebSocket, detail: str) -> None:
    try:
        await websocket.send_json({"type": "error", "detail": detail})
    except Exception:
        pass
