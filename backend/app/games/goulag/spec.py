"""Branchement du Goulag sur la plateforme : la GameSpec du jeu."""

from __future__ import annotations

import random

from app.games.base import AfterMove, Event, GameSpec, GameStatus
from app.games.goulag import bots
from app.games.goulag.engine import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    Action,
    GameState,
    Phase,
    Suit,
    add_player,
    announce,
    can_charge,
    choose_suit,
    choose_target,
    create_game,
    remove_player,
    set_ready,
)
from app.games.goulag.views import game_view
from app.rooms.manager import Room, Seat


class Goulag(GameSpec):
    slug = "goulag"
    name = "Goulag"
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
        if state.status is not GameStatus.PLAYING:
            return None
        # Pendant une résurrection, c'est le mort qui doit agir.
        if state.phase is Phase.REVIVAL and state.reviving is not None:
            return state.reviving
        return state.turn_index

    # --- Vue et actions --------------------------------------------------------

    def view(self, room: Room, seat: int) -> dict:
        return game_view(room, seat)

    def handle_action(
        self, room: Room, seat: int, action: str, message: dict
    ) -> list[Event] | None:
        state = room.state
        if action == "ready":
            return set_ready(state, seat, bool(message.get("ready", True)))
        if action == "announce":
            return announce(state, seat, Action(str(message["action_kind"])))
        if action == "target":
            return choose_target(state, seat, int(message["seat"]))
        if action == "suit":
            return choose_suit(state, seat, Suit(str(message["suit"])))
        return None

    def auto_play(self, room: Room, seat: int) -> list[Event]:
        """Temps écoulé : le coup le plus neutre pour ce siège."""
        state = room.state
        if state.phase is Phase.REVIVAL:
            return choose_suit(state, seat, random.choice(list(Suit)))
        if state.phase is Phase.TARGET:
            if state.pending_action is Action.DEFEND:
                return choose_target(state, seat, seat)
            others = [i for i in state.alive_indices() if i != seat]
            return choose_target(state, seat, random.choice(others))
        if can_charge(state, seat):
            return announce(state, seat, Action.CHARGE)
        events = announce(state, seat, Action.DEFEND)
        return events + choose_target(state, seat, seat)

    # --- Fin de partie -----------------------------------------------------------

    def results(self, room: Room) -> tuple[int, int] | None:
        players = room.state.players
        winner = next((i for i, p in enumerate(players) if p.finish_rank == 1), None)
        if winner is None:
            return None
        loser = max(range(len(players)), key=lambda i: players[i].finish_rank or 0)
        return winner, loser

    # --- Bots --------------------------------------------------------------------

    def add_bot(self, room: Room, difficulty: str) -> Seat:
        return bots.add_bot(room, difficulty)

    def schedule_bots(self, room: Room, after_move: AfterMove) -> None:
        bots.schedule(room, after_move)
