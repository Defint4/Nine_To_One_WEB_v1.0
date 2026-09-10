"use client";

import { useCallback } from "react";
import { useRoomSocket, type RoomSocket } from "@/lib/useRoomSocket";
import type { ActionKind, RoomView, SuitName } from "./types";

/* Le socket de table, enrichi des actions du Goulag. */

export type GoulagSocket = RoomSocket<RoomView> & {
  setReady: (ready: boolean) => void;
  announce: (kind: ActionKind) => void;
  target: (seat: number) => void;
  chooseSuit: (suit: SuitName) => void;
};

export function useGoulagSocket(code: string, token: string | null): GoulagSocket {
  const socket = useRoomSocket<RoomView>(code, token);
  const { send } = socket;
  return {
    ...socket,
    setReady: useCallback((ready) => send({ action: "ready", ready }), [send]),
    announce: useCallback((kind) => send({ action: "announce", action_kind: kind }), [send]),
    target: useCallback((seat) => send({ action: "target", seat }), [send]),
    chooseSuit: useCallback((suit) => send({ action: "suit", suit }), [send]),
  };
}
