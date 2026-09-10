"""État d'une partie de Goulag.

Structures pures (aucune I/O) : le moteur (game.py) les fait évoluer, la couche
réseau les sérialise et filtre ce que chaque joueur a le droit de voir.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

from app.games.base import GameStatus

from .cards import Card, Suit

__all__ = ["Action", "GameState", "GameStatus", "Phase", "PlayerState", "Suit"]


class Action(StrEnum):
    DEFEND = "defend"  # la carte piochée remplace une défense (la sienne ou celle d'un autre)
    CHARGE = "charge"  # la carte piochée est posée face cachée à côté des vies (2 max)
    ATTACK = "attack"  # la carte piochée (+ charges) frappe un adversaire


class Phase(StrEnum):
    """Où en est le tour courant."""

    ACTION = "action"  # le joueur au trait annonce défense / charge / attaque, à l'aveugle
    TARGET = "target"  # la carte est piochée et vue : il désigne la cible
    REVIVAL = "revival"  # un joueur vient de mourir : il choisit une couleur


@dataclass(slots=True)
class PlayerState:
    name: str
    lives: list[Card] = field(default_factory=list)  # 1 ou 2 cartes visibles, leur somme = vies
    defense: Card | None = None  # bouclier visible
    charges: list[Card] = field(default_factory=list)  # face cachée, jamais vues (2 max)
    ready: bool = False
    # None = en jeu ; sinon rang final (1 = vainqueur, n = premier éliminé).
    finish_rank: int | None = None

    @property
    def life_total(self) -> int:
        return sum(c.value for c in self.lives)

    @property
    def alive(self) -> bool:
        return self.finish_rank is None

    @property
    def hawk_eye(self) -> bool:
        """« Œil de faucon » : il ne lui reste qu'un As de vie."""
        return len(self.lives) == 1 and self.lives[0].value == 1

    @property
    def card_count(self) -> int:
        return len(self.lives) + (1 if self.defense else 0) + len(self.charges)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "lives": [c.to_dict() for c in self.lives],
            "defense": self.defense.to_dict() if self.defense else None,
            "charges": [c.to_dict() for c in self.charges],
            "ready": self.ready,
            "finish_rank": self.finish_rank,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlayerState:
        return cls(
            name=data["name"],
            lives=[Card.from_dict(c) for c in data["lives"]],
            defense=Card.from_dict(data["defense"]) if data["defense"] else None,
            charges=[Card.from_dict(c) for c in data["charges"]],
            ready=data["ready"],
            finish_rank=data["finish_rank"],
        )


@dataclass(slots=True)
class GameState:
    players: list[PlayerState]
    draw_pile: list[Card] = field(default_factory=list)  # la pioche (le dessus = fin de liste)
    discard: list[Card] = field(default_factory=list)  # la défausse (le dessus = fin de liste)
    status: GameStatus = GameStatus.LOBBY
    turn_index: int = 0
    phase: Phase = Phase.ACTION
    # Pendant TARGET : l'action annoncée et la carte piochée, vue par le joueur au trait.
    pending_action: Action | None = None
    drawn: Card | None = None
    # Pendant REVIVAL : le siège du mort qui doit choisir sa couleur.
    reviving: int | None = None
    # Nombre de joueurs déjà éliminés (pour finish_rank).
    eliminated: int = 0
    # Hasard de la partie (mélanges, tirage du premier joueur), rejouable avec une graine.
    rng: random.Random = field(default_factory=random.Random)

    @property
    def current_player(self) -> PlayerState:
        return self.players[self.turn_index]

    def alive_indices(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if p.alive]

    def to_dict(self) -> dict:
        return {
            "players": [p.to_dict() for p in self.players],
            "draw_pile": [c.to_dict() for c in self.draw_pile],
            "discard": [c.to_dict() for c in self.discard],
            "status": self.status.value,
            "turn_index": self.turn_index,
            "phase": self.phase.value,
            "pending_action": self.pending_action.value if self.pending_action else None,
            "drawn": self.drawn.to_dict() if self.drawn else None,
            "reviving": self.reviving,
            "eliminated": self.eliminated,
        }
