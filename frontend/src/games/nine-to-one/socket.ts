"use client";

import { useCallback } from "react";
import { useRoomSocket, type RoomSocket } from "@/lib/useRoomSocket";
import type { RoomView } from "./types";

/* Le socket de table, enrichi des actions de Nine to One. */

export type NineToOneSocket = RoomSocket<RoomView> & {
  swap: (handIndex: number, faceUpIndex: number) => void;
  setReady: (ready: boolean) => void;
  play: (value: number, count: number, direction?: ">=" | "<=") => void;
  flip: (index: number) => void;
  chase: (count: number) => void;
  chaseFlip: (index: number) => void;
};

export function useNineToOneSocket(code: string, token: string | null): NineToOneSocket {
  const socket = useRoomSocket<RoomView>(code, token);
  const { send } = socket;
  return {
    ...socket,
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
  };
}
