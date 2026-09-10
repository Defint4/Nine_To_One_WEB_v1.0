"use client";

import { useEffect, useState } from "react";
import { listRooms, liveRoomsUrl } from "./api";
import type { OpenRoom } from "./types";

/* Les tables ouvertes d'un jeu, en direct : un WebSocket pousse la liste à chaque
   changement, la première liste arrive en REST pour ne pas attendre la connexion.
   Coupure réseau : on retente avec un léger backoff, et on garde la dernière liste. */

export function useOpenRooms(game: string): { rooms: OpenRoom[]; ready: boolean } {
  const [rooms, setRooms] = useState<OpenRoom[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout>;

    listRooms(game)
      .then((list) => {
        if (!disposed) {
          setRooms(list);
          setReady(true);
        }
      })
      .catch(() => {
        /* le WebSocket fournira la liste */
      });

    function connect() {
      socket = new WebSocket(liveRoomsUrl(game));
      socket.onmessage = (raw) => {
        const msg = JSON.parse(raw.data) as { type: string; rooms?: OpenRoom[] };
        if (msg.type === "rooms" && msg.rooms) {
          retry = 0;
          setRooms(msg.rooms);
          setReady(true);
        }
      };
      socket.onclose = () => {
        if (disposed) return;
        timer = setTimeout(connect, Math.min(500 * 2 ** retry, 8000));
        retry += 1;
      };
    }
    connect();

    // Retour au premier plan : la connexion a pu être tuée sans événement.
    function onVisible() {
      if (document.visibilityState !== "visible" || disposed) return;
      if (!socket || socket.readyState === WebSocket.CLOSED) connect();
    }
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      disposed = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      socket?.close();
    };
  }, [game]);

  return { rooms, ready };
}
