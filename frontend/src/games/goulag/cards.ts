import type { CardT } from "@/lib/types";

/* Le deck SVG indexe l'As en 14 ; au Goulag il vaut 1. On convertit à l'affichage. */
export function face(card: CardT): CardT {
  return card.value === 1 ? { value: 14, suit: card.suit } : card;
}

export const SUIT_GLYPH: Record<CardT["suit"], string> = {
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
  spades: "♠",
};

export const SUIT_LABEL: Record<CardT["suit"], string> = {
  hearts: "Cœur",
  diamonds: "Carreau",
  clubs: "Trèfle",
  spades: "Pique",
};
