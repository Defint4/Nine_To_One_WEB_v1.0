"""Erreurs du moteur de jeu. Toutes héritent de GameError pour un catch unique côté API."""

from app.games.base import GameError

__all__ = ["GameError", "IllegalMove", "InvalidAction", "NotYourTurn"]


class NotYourTurn(GameError):
    pass


class IllegalMove(GameError):
    pass


class InvalidAction(GameError):
    """Action impossible dans l'état courant (mauvaise phase, index invalide...)."""
