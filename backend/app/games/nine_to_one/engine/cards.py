"""Cartes et deck du Nine to One.

Valeurs numériques : 2 à 14 (11 = Valet, 12 = Dame, 13 = Roi, 14 = As).
L'ordre de jeu est 3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J < Q < K < A ;
le 2, le 7, le 9 et le 10 portent des pouvoirs spéciaux (voir game.py).
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


MIN_VALUE = 2
MAX_VALUE = 14  # As


@dataclass(frozen=True, slots=True)
class Card:
    value: int  # 2..14
    suit: Suit

    def to_dict(self) -> dict:
        return {"value": self.value, "suit": self.suit.value}

    @classmethod
    def from_dict(cls, data: dict) -> Card:
        return cls(value=data["value"], suit=Suit(data["suit"]))


def new_deck() -> list[Card]:
    """Deck standard de 52 cartes, non mélangé."""
    return [Card(v, s) for v in range(MIN_VALUE, MAX_VALUE + 1) for s in Suit]


def shuffled_deck(seed: int | None = None) -> list[Card]:
    deck = new_deck()
    random.Random(seed).shuffle(deck)
    return deck
