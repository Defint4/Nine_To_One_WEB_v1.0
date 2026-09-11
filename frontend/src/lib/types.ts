/* Types communs à la plateforme : identité, tables, messages WebSocket.
   Chaque jeu étend BaseRoomView / BasePlayerView dans src/games/<slug>/types.ts. */

export type Suit = "hearts" | "diamonds" | "clubs" | "spades";

export type CardT = { value: number; suit: Suit };

export type BotDifficulty = "easy" | "normal" | "hard";

export const BOT_LABELS: Record<BotDifficulty, string> = {
  easy: "Facile",
  normal: "Normal",
  hard: "Difficile",
};

/* Fiche d'un siège, telle que la plateforme la décrit (le jeu y ajoute ses champs). */
export type BasePlayerView = {
  seat: number;
  pseudo: string;
  avatar: string;
  connected: boolean;
  bot: BotDifficulty | null;
};

export type BaseRoomView = {
  code: string;
  game: string;
  status: "lobby" | "playing" | "finished";
  your_seat: number;
  turn: number | null;
  players: BasePlayerView[];
  turn_seconds: number;
  turn_remaining: number | null;
};

export type GameEvent = { type: string; [key: string]: unknown };

export type ChatEntry = { type: "chat"; seat: number; text: string };

export type ServerMessage<V extends BaseRoomView = BaseRoomView> =
  | { type: "state"; events: GameEvent[]; view: V; chat?: ChatEntry[] }
  | ChatEntry
  | { type: "emote"; seat: number; emote: string; target: number | null }
  | { type: "rematch"; code: string }
  | { type: "error"; detail: string };

export type GameStats = { played: number; won: number; lost: number };

export type PlayerProfile = {
  id: string;
  pseudo: string;
  avatar: string;
  /* Par jeu (clé = slug) ; absent si jamais joué. */
  stats: Record<string, GameStats>;
};

export const NO_STATS: GameStats = { played: 0, won: 0, lost: 0 };

export type LeaderboardEntry = GameStats & {
  rank: number;
  id: string;
  pseudo: string;
  avatar: string;
};

export type LeaderboardPage = {
  total: number;
  entries: LeaderboardEntry[];
  /* La place du joueur demandé, null s'il n'a jamais joué. */
  me: LeaderboardEntry | null;
};

export type OpenRoom = {
  code: string;
  game: string;
  players: { pseudo: string; avatar: string }[];
  seats_taken: number;
  seats_max: number;
};
