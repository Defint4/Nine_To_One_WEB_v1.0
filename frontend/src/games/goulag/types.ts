import type { BasePlayerView, BaseRoomView, CardT } from "@/lib/types";

/* Au Goulag une carte vaut sa valeur : As = 1 … Roi = 13 (voir cards.ts pour l'affichage). */

export type Phase = "action" | "target" | "revival";
export type ActionKind = "defend" | "charge" | "attack";
export type SuitName = "hearts" | "diamonds" | "clubs" | "spades";

export type PlayerView = BasePlayerView & {
  ready: boolean;
  finish_rank: number | null;
  alive: boolean;
  lives: CardT[];
  life_total: number;
  defense: CardT | null;
  charges: number;
  hawk_eye: boolean;
};

export type RoomView = Omit<BaseRoomView, "players"> & {
  players: PlayerView[];
  phase: Phase | null;
  pending_action: "defend" | "attack" | null;
  /* Œil de faucon : la carte du dessus, visible seulement par le joueur concerné. */
  peek: CardT | null;
  reviving: number | null;
  draw_count: number;
  discard_count: number;
  discard_top: CardT | null;
  can_charge: boolean;
  must_choose_suit: boolean;
  alive_count: number;
  you_alive: boolean;
};
