"""Moteur de jeu du Goulag (pur, sans I/O)."""

from .cards import Card, Suit, new_deck, shuffled_deck
from .errors import GameError, IllegalMove, InvalidAction, NotYourTurn
from .game import (
    DEAL_SIZE,
    MAX_CHARGES,
    MAX_PLAYERS,
    MIN_PLAYERS,
    add_player,
    announce,
    can_charge,
    choose_suit,
    choose_target,
    create_game,
    peek,
    remove_player,
    set_ready,
)
from .state import Action, GameState, GameStatus, Phase, PlayerState

__all__ = [
    "Card",
    "Suit",
    "new_deck",
    "shuffled_deck",
    "GameError",
    "IllegalMove",
    "InvalidAction",
    "NotYourTurn",
    "DEAL_SIZE",
    "MAX_CHARGES",
    "MAX_PLAYERS",
    "MIN_PLAYERS",
    "add_player",
    "announce",
    "can_charge",
    "choose_suit",
    "choose_target",
    "create_game",
    "peek",
    "remove_player",
    "set_ready",
    "Action",
    "GameState",
    "GameStatus",
    "Phase",
    "PlayerState",
]
