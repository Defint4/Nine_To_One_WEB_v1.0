import type { LeaderboardPage, OpenRoom, PlayerProfile } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function wsUrl(code: string, token: string): string {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/api/rooms/${code}/ws?token=${encodeURIComponent(token)}`;
}

/* Liste des tables ouvertes d'un jeu, poussée à chaque changement. */
export function liveRoomsUrl(game: string): string {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/api/rooms/live?game=${encodeURIComponent(game)}`;
}

export class ApiError extends Error {
  constructor(public status: number, detail: string) {
    super(detail);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = "Le serveur ne répond pas comme prévu.";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* réponse sans corps JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

function authed(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export type RoomRef = { code: string; game: string };

export function enter(pseudo: string, avatar: string) {
  return request<{ player: PlayerProfile; token: string }>("/api/players/enter", {
    method: "POST",
    body: JSON.stringify({ pseudo, avatar }),
  });
}

export function fetchMe(token: string) {
  return request<PlayerProfile>("/api/players/me", { headers: authed(token) });
}

export function fetchPlayerByPseudo(pseudo: string) {
  return request<PlayerProfile>(`/api/players/by-pseudo/${encodeURIComponent(pseudo)}`);
}

export const LEADERBOARD_PAGE = 25;

/* Une page du classement d'un jeu (slug) ou de tous les jeux (null). `me` : le pseudo
   dont on veut la place, renvoyée à part même si elle n'est pas dans la page. */
export function fetchLeaderboard(game: string | null, offset: number, me?: string) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(LEADERBOARD_PAGE) });
  if (game) params.set("game", game);
  if (me) params.set("me", me);
  return request<LeaderboardPage>(`/api/players/leaderboard?${params}`);
}

export function createRoom(token: string, game: string) {
  return request<RoomRef>("/api/rooms", {
    method: "POST",
    headers: authed(token),
    body: JSON.stringify({ game }),
  });
}

export type RoomStatus = RoomRef & {
  status: "lobby" | "playing" | "finished";
  seated: boolean;
};

/* L'état d'une table (404 si elle n'existe plus) : sert à vérifier qu'une partie
   mémorisée se reprend vraiment avant de le proposer. */
export function fetchRoom(token: string, code: string) {
  return request<RoomStatus>(`/api/rooms/${code}`, { headers: authed(token) });
}

export function joinRoom(token: string, code: string) {
  return request<RoomRef>(`/api/rooms/${code}/join`, {
    method: "POST",
    headers: authed(token),
  });
}

export function listRooms(game: string) {
  return request<OpenRoom[]>(`/api/rooms?game=${encodeURIComponent(game)}`);
}
