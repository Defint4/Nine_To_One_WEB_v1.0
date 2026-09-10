import type { BasePlayerView, BaseRoomView, CardT } from "@/lib/types";

export type Constraint = { comparator: ">=" | "<="; value: number };

export type PlayerView = BasePlayerView & {
  ready: boolean;
  finish_rank: number | null;
  hand_count: number;
  face_up: CardT[];
  face_down_count: number;
  hand: CardT[] | null;
};

export type RoomView = Omit<BaseRoomView, "players"> & {
  players: PlayerView[];
  constraint: Constraint | null;
  required_first_value: number | null;
  pile: CardT[];
  draw_count: number;
  discard_count: number;
  playable_values: number[];
  must_flip: boolean;
  stats: { moves: number; pickups: Record<string, number> };
  last_play_seat: number | null;
  chase_value: number | null;
};
