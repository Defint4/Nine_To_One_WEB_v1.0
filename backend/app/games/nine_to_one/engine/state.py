"""État d'une partie de Nine to One.

Structures pures (aucune I/O) : le moteur (game.py) les fait évoluer,
la couche réseau les sérialise et filtre ce que chaque joueur a le droit de voir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.games.base import GameStatus

from .cards import Card

# Statut commun à la plateforme : en lobby, échange initial main <-> cartes visibles,
# en attente des « prêt ».
__all__ = ["Comparator", "Constraint", "GameState", "GameStatus", "PlayerState"]


class Comparator(StrEnum):
    GTE = ">="
    LTE = "<="


@dataclass(slots=True)
class Constraint:
    """Contrainte posée par un 7 ou un 9 sur le prochain coup."""

    comparator: Comparator
    value: int

    def allows(self, value: int) -> bool:
        if self.comparator is Comparator.GTE:
            return value >= self.value
        return value <= self.value

    def to_dict(self) -> dict:
        return {"comparator": self.comparator.value, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict) -> Constraint:
        return cls(comparator=Comparator(data["comparator"]), value=data["value"])


@dataclass(slots=True)
class PlayerState:
    name: str
    hand: list[Card] = field(default_factory=list)
    face_up: list[Card] = field(default_factory=list)  # 3 cartes visibles posées sur les cachées
    face_down: list[Card] = field(default_factory=list)  # 3 cartes face cachée
    ready: bool = False
    finish_rank: int | None = None  # 1 = premier à avoir vidé ses cartes ; None = encore en jeu

    @property
    def finished(self) -> bool:
        return self.finish_rank is not None

    @property
    def card_count(self) -> int:
        return len(self.hand) + len(self.face_up) + len(self.face_down)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hand": [c.to_dict() for c in self.hand],
            "face_up": [c.to_dict() for c in self.face_up],
            "face_down": [c.to_dict() for c in self.face_down],
            "ready": self.ready,
            "finish_rank": self.finish_rank,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlayerState:
        return cls(
            name=data["name"],
            hand=[Card.from_dict(c) for c in data["hand"]],
            face_up=[Card.from_dict(c) for c in data["face_up"]],
            face_down=[Card.from_dict(c) for c in data["face_down"]],
            ready=data["ready"],
            finish_rank=data["finish_rank"],
        )


@dataclass(slots=True)
class GameState:
    players: list[PlayerState]
    draw_pile: list[Card] = field(default_factory=list)  # la pioche
    pile: list[Card] = field(default_factory=list)  # le tas central
    discard: list[Card] = field(default_factory=list)  # la défausse (cartes coupées)
    status: GameStatus = GameStatus.LOBBY
    turn_index: int = 0
    constraint: Constraint | None = None
    # Valeur imposée pour le tout premier coup (plus petite carte hors 2), None ensuite.
    required_first_value: int | None = None
    # Dernier joueur à avoir posé : c'est lui qui rejoue quand son coup fait ramasser le tas.
    last_play_index: int | None = None
    # « Bonne pioche » armée : le dernier coup a fait piocher une carte de la valeur posée.
    chase_armed: bool = False
    # Nombre de rangs déjà attribués (pour finish_rank).
    ranks_assigned: int = 0

    @property
    def current_player(self) -> PlayerState:
        return self.players[self.turn_index]

    def active_indices(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if not p.finished]

    def to_dict(self) -> dict:
        return {
            "players": [p.to_dict() for p in self.players],
            "draw_pile": [c.to_dict() for c in self.draw_pile],
            "pile": [c.to_dict() for c in self.pile],
            "discard": [c.to_dict() for c in self.discard],
            "status": self.status.value,
            "turn_index": self.turn_index,
            "constraint": self.constraint.to_dict() if self.constraint else None,
            "required_first_value": self.required_first_value,
            "last_play_index": self.last_play_index,
            "chase_armed": self.chase_armed,
            "ranks_assigned": self.ranks_assigned,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GameState:
        return cls(
            players=[PlayerState.from_dict(p) for p in data["players"]],
            draw_pile=[Card.from_dict(c) for c in data["draw_pile"]],
            pile=[Card.from_dict(c) for c in data["pile"]],
            discard=[Card.from_dict(c) for c in data["discard"]],
            status=GameStatus(data["status"]),
            turn_index=data["turn_index"],
            constraint=Constraint.from_dict(data["constraint"]) if data["constraint"] else None,
            required_first_value=data["required_first_value"],
            last_play_index=data["last_play_index"],
            chase_armed=data.get("chase_armed", False),
            ranks_assigned=data["ranks_assigned"],
        )
