"""Erreurs du moteur de jeu. Toutes héritent de GameError pour un catch unique côté API."""


class GameError(Exception):
    """Erreur de règle ou d'action invalide."""


class NotYourTurn(GameError):
    pass


class IllegalMove(GameError):
    pass


class InvalidAction(GameError):
    """Action impossible dans l'état courant (mauvaise phase, index invalide...)."""
