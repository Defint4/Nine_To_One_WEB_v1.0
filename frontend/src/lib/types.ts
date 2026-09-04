export type Suit = "hearts" | "diamonds" | "clubs" | "spades";

export type CardT = { value: number; suit: Suit };

export type Constraint = { comparator: ">=" | "<="; value: number };

export type BotDifficulty = "easy" | "normal" | "hard";

export const BOT_LABELS: Record<BotDifficulty, string> = {
  easy: "Facile",
  normal: "Normal",
  hard: "Difficile",
};

export type PlayerView = {
  seat: number;
  pseudo: string;
  avatar: string;
  connected: boolean;
  bot: BotDifficulty | null;
  ready: boolean;
  finish_rank: number | null;
  hand_count: number;
  face_up: CardT[];
  face_down_count: number;
  hand: CardT[] | null;
};

export type RoomView = {
  code: string;
  status: "lobby" | "playing" | "finished";
  your_seat: number;
  turn: number | null;
  constraint: Constraint | null;
  required_first_value: number | null;
  pile: CardT[];
  draw_count: number;
  discard_count: number;
  players: PlayerView[];
  playable_values: number[];
  must_flip: boolean;
  turn_seconds: number;
  turn_remaining: number | null;
  stats: { moves: number; pickups: Record<string, number> };
  last_play_seat: number | null;
  chase_value: number | null;
};

export type GameEvent = { type: string; [key: string]: unknown };

export type ChatEntry = { type: "chat"; seat: number; text: string };

export type ServerMessage =
  | { type: "state"; events: GameEvent[]; view: RoomView; chat?: ChatEntry[] }
  | ChatEntry
  | { type: "emote"; seat: number; emote: string; target: number | null }
  | { type: "rematch"; code: string }
  | { type: "error"; detail: string };

export type PlayerProfile = {
  id: string;
  pseudo: string;
  avatar: string;
  games_played: number;
  games_won: number;
  games_lost: number;
};

export type OpenRoom = {
  code: string;
  players: { pseudo: string; avatar: string }[];
  seats_taken: number;
  seats_max: number;
};
