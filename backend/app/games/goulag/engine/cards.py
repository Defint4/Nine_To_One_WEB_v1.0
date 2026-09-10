"""Cartes et paquet du Goulag.

Valeurs numériques : 1 à 13 (1 = As, 11 = Valet, 12 = Dame, 13 = Roi). Au Goulag une
carte vaut sa valeur, rien de plus : vies, défense et attaques s'additionnent.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum


class Suit(StrEnum):
    HEARTS = "hearts"
    DIAMONDS = "diamonds"
    CLUBS = "clubs"
    SPADES = "spades"


MIN_VALUE = 1  # As
MAX_VALUE = 13  # Roi


@dataclass(frozen=True, slots=True)
class Card:
    value: int  # 1..13
    suit: Suit

    def to_dict(self) -> dict:
        return {"value": self.value, "suit": self.suit.value}

    @classmethod
    def from_dict(cls, data: dict) -> Card:
        return cls(value=data["value"], suit=Suit(data["suit"]))


def new_deck() -> list[Card]:
    """Paquet standard de 52 cartes, non mélangé."""
    return [Card(v, s) for v in range(MIN_VALUE, MAX_VALUE + 1) for s in Suit]


def shuffled_deck(rng: random.Random) -> list[Card]:
    deck = new_deck()
    rng.shuffle(deck)
    return deck
