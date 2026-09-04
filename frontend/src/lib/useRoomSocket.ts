"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { joinRoom, wsUrl } from "./api";
import { sfx } from "./sound";
import type { BotDifficulty, ChatEntry, GameEvent, RoomView, ServerMessage } from "./types";

export type EmoteEvent = { id: number; seat: number; emote: string; target: number | null };

export type RoomSocket = {
  view: RoomView | null;
  chat: ChatEntry[];
  emotes: EmoteEvent[];
  error: string | null;
  closedReason: string | null;
  rematchCode: string | null;
  swap: (handIndex: number, faceUpIndex: number) => void;
  setReady: (ready: boolean) => void;
  play: (value: number, count: number, direction?: ">=" | "<=") => void;
  flip: (index: number) => void;
  chase: (count: number) => void;
  chaseFlip: (index: number) => void;
  sendChat: (text: string) => void;
  sendEmote: (emote: string, target?: number) => void;
  setTurnSeconds: (seconds: number) => void;
  addBot: (difficulty: BotDifficulty) => void;
  removeBot: (seat: number) => void;
  rematch: () => void;
  leave: () => void;
  onEvents: (handler: (events: GameEvent[], nextView: RoomView) => void) => void;
};

const CLOSE_REASONS: Record<number, string> = {
  4401: "Session expirée : reviens à l'accueil pour entrer à nouveau.",
  4403: "Tu n'es pas assis à cette table.",
  4404: "Cette table n'existe plus.",
};

let emoteId = 0;

export function useRoomSocket(code: string, token: string | null): RoomSocket {
  const [view, setView] = useState<RoomView | null>(null);
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [emotes, setEmotes] = useState<EmoteEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [closedReason, setClosedReason] = useState<string | null>(null);
  const [rematchCode, setRematchCode] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const eventsHandlerRef = useRef<((events: GameEvent[], nextView: RoomView) => void) | null>(
    null
  );
  const retryRef = useRef(0);
  const rejoinRef = useRef(0);

  useEffect(() => {
    if (!token) return;
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const socket = new WebSocket(wsUrl(code, token!));
      socketRef.current = socket;

      socket.onmessage = (raw) => {
        const msg = JSON.parse(raw.data) as ServerMessage;
        if (msg.type === "state") {
          retryRef.current = 0;
          setView(msg.view);
          if (msg.chat) setChat(msg.chat);
          if (msg.events.length) eventsHandlerRef.current?.(msg.events, msg.view);
        } else if (msg.type === "chat") {
          setChat((prev) => [...prev.slice(-99), msg]);
          sfx.pop();
        } else if (msg.type === "emote") {
          const id = ++emoteId;
          setEmotes((prev) => [
            ...prev,
            { id, seat: msg.seat, emote: msg.emote, target: msg.target ?? null },
          ]);
          setTimeout(() => setEmotes((prev) => prev.filter((e) => e.id !== id)), 2600);
        } else if (msg.type === "rematch") {
          setRematchCode(msg.code);
        } else if (msg.type === "error") {
          setError(msg.detail);
          setTimeout(() => setError(null), 3500);
        }
      };

      socket.onclose = (event) => {
        if (disposed || socketRef.current !== socket) return;
        if (event.code === 4403 && rejoinRef.current < 2) {
          // Siège expiré (délai de grâce dépassé) : on se rassoit puis on se reconnecte.
          rejoinRef.current += 1;
          joinRoom(token!, code)
            .then(() => connect())
            .catch((e) =>
              setClosedReason(e instanceof Error ? e.message : "Impossible de rejoindre.")
            );
          return;
        }
        const terminal = CLOSE_REASONS[event.code];
        if (terminal) {
          setClosedReason(terminal);
          return;
        }
        // Coupure réseau ou serveur : on retente avec un léger backoff.
        const delay = Math.min(500 * 2 ** retryRef.current, 8000);
        retryRef.current += 1;
        retryTimer = setTimeout(connect, delay);
      };
    }

    connect();

    // Retour au premier plan sur mobile : le navigateur a pu suspendre ou tuer
    // la connexion sans événement de fermeture. On resynchronise ou on reconnecte.
    function onVisible() {
      if (document.visibilityState !== "visible") return;
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "sync" }));
      } else if (!socket || socket.readyState === WebSocket.CLOSED) {
        connect();
      }
    }
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      document.removeEventListener("visibilitychange", onVisible);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [code, token]);

  const send = useCallback((payload: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
  }, []);

  return {
    view,
    chat,
    emotes,
    error,
    closedReason,
    rematchCode,
    swap: useCallback(
      (handIndex, faceUpIndex) =>
        send({ action: "swap", hand_index: handIndex, face_up_index: faceUpIndex }),
      [send]
    ),
    setReady: useCallback((ready) => send({ action: "ready", ready }), [send]),
    play: useCallback(
      (value, count, direction) => send({ action: "play", value, count, direction }),
      [send]
    ),
    flip: useCallback((index) => send({ action: "flip", index }), [send]),
    chase: useCallback((count) => send({ action: "chase", count }), [send]),
    chaseFlip: useCallback((index) => send({ action: "chase_flip", index }), [send]),
    sendChat: useCallback((text) => send({ action: "chat", text }), [send]),
    sendEmote: useCallback((emote, target) => send({ action: "emote", emote, target }), [send]),
    setTurnSeconds: useCallback(
      (seconds) => send({ action: "config", turn_seconds: seconds }),
      [send]
    ),
    addBot: useCallback((difficulty) => send({ action: "add_bot", difficulty }), [send]),
    removeBot: useCallback((seat) => send({ action: "remove_bot", seat }), [send]),
    rematch: useCallback(() => send({ action: "rematch" }), [send]),
    leave: useCallback(() => send({ action: "leave" }), [send]),
    onEvents: useCallback((handler) => {
      eventsHandlerRef.current = handler;
    }, []),
  };
}
