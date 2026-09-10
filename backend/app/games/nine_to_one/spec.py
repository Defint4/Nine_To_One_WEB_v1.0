"""Branchement de Nine to One sur la plateforme : la GameSpec du jeu.

Le moteur (engine/) reste pur ; ici on traduit les messages WebSocket en appels
au moteur, on décrit la vue de chaque siège et on cadence les bots.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from app.games.base import AfterMove, Event, GameSpec, GameStatus
from app.games.nine_to_one import bots
from app.games.nine_to_one.engine import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    Comparator,
    GameState,
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
from app.games.nine_to_one.views import game_view
from app.rooms.manager import Room, Seat


@dataclass
class RoomData:
    """Ce que Nine to One retient par table en plus de l'état du moteur."""

    # Statistiques de la manche en cours (pour l'écran de fin).
    moves: int = 0
    pickups: dict[int, int] = field(default_factory=dict)
    # Bots : mémoire des événements publics (cartes vues).
    bot_memory: Any = None
    # Journal de la manche (distribution initiale + événements) pour analyser
    # les parties contre les bots.
    initial_state: dict | None = None
    history: list[dict] = field(default_factory=list)


class NineToOne(GameSpec):
    slug = "nine-to-one"
    name = "Nine to One"
    min_players = MIN_PLAYERS
    max_players = MAX_PLAYERS
    bot_difficulties = bots.DIFFICULTIES

    # --- État ----------------------------------------------------------------

    def create_state(self, creator_pseudo: str) -> GameState:
        return create_game(creator_pseudo)

    def add_player(self, state: GameState, pseudo: str) -> None:
        add_player(state, pseudo)

    def remove_player(self, state: GameState, seat: int) -> None:
        remove_player(state, seat)

    def rotate_players(self, state: GameState, k: int) -> None:
        state.players[:] = state.players[k:] + state.players[:k]

    def status(self, state: GameState) -> GameStatus:
        return state.status

    def current_turn(self, state: GameState) -> int | None:
        return state.turn_index if state.status is GameStatus.PLAYING else None

    def new_room_data(self) -> RoomData:
        return RoomData()

    # --- Vue et actions --------------------------------------------------------

    def view(self, room: Room, seat: int) -> dict:
        return game_view(room, seat)

    def handle_action(
        self, room: Room, seat: int, action: str, message: dict
    ) -> list[Event] | None:
        state = room.state
        if action == "swap":
            swap_cards(state, seat, int(message["hand_index"]), int(message["face_up_index"]))
            return []
        if action == "ready":
            return set_ready(state, seat, bool(message.get("ready", True)))
        if action == "play":
            direction = message.get("direction")
            return play_cards(
                state,
                seat,
                int(message["value"]),
                count=int(message.get("count", 1)),
                direction=Comparator(direction) if direction else None,
            )
        if action == "flip":
            return flip_face_down(state, seat, int(message["index"]))
        if action == "chase":
            return chase_play(state, seat, int(message.get("count", 1)))
        if action == "chase_flip":
            return chase_flip(state, seat, int(message["index"]))
        return None

    def auto_play(self, room: Room, seat: int) -> list[Event]:
        """Temps écoulé : le serveur joue le coup le plus simple pour le joueur."""
        state = room.state
        player = state.players[seat]
        if not player.hand:
            return flip_face_down(state, seat, random.randrange(len(player.face_down)))
        value = min(playable_values(state, seat))
        direction = Comparator.GTE if value == 7 else None
        return play_cards(state, seat, value, count=1, direction=direction)

    # --- Fin de partie -----------------------------------------------------------

    def results(self, room: Room) -> tuple[int, int] | None:
        players = room.state.players
        winner = next((i for i, p in enumerate(players) if p.finish_rank == 1), None)
        if winner is None:
            return None
        loser = max(range(len(players)), key=lambda i: players[i].finish_rank or 0)
        return winner, loser

    def on_events(self, room: Room, events: list[Event]) -> None:
        data: RoomData = room.data
        for event in events:
            if event["type"] == "cards_played":
                data.moves += 1
            elif event["type"] == "pile_picked_up":
                seat = event["player"]
                data.pickups[seat] = data.pickups.get(seat, 0) + 1
            elif event["type"] == "game_started":
                data.initial_state = room.state.to_dict()
                data.history = []
        data.history.extend(events)
        bots.observe(room, events)

    def on_game_over(self, room: Room) -> None:
        bots.log_game(room)

    # --- Bots --------------------------------------------------------------------

    def add_bot(self, room: Room, difficulty: str) -> Seat:
        return bots.add_bot(room, difficulty)

    def schedule_bots(self, room: Room, after_move: AfterMove) -> None:
        bots.schedule(room, after_move)
