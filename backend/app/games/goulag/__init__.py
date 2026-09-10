"""Goulag : jeu de cartes de combat (2 à 6 joueurs), bots Facile et Normal.

engine/    règles pures (aucune I/O), testées dans tests/
views.py   ce que chaque siège a le droit de voir
bots.py    Facile (hasard) / Normal (heuristique), cadencement
spec.py    branchement sur la plateforme (GameSpec)
"""

from app.games.goulag.spec import Goulag

__all__ = ["Goulag"]
