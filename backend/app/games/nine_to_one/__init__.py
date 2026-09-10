"""Nine to One : jeu de cartes multijoueur (2 à 5 joueurs), bots à trois niveaux.

engine/    règles pures (aucune I/O), testées dans tests/
views.py   ce que chaque siège a le droit de voir
bots.py    Facile / Normal / Difficile (réseau numpy dans botbrain.py, poids *.npz)
spec.py    branchement sur la plateforme (GameSpec)
"""

from app.games.nine_to_one.spec import NineToOne

__all__ = ["NineToOne"]
