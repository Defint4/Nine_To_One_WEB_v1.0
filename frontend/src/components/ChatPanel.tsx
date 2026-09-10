"use client";

import { useEffect, useRef, useState } from "react";
import type { BaseRoomView } from "@/lib/types";
import type { RoomSocket } from "@/lib/useRoomSocket";

/* Le chat complet : tout l'historique + saisie. Affiché dans une bottom-sheet. */
export default function ChatPanel({ socket, view }: { socket: RoomSocket; view: BaseRoomView }) {
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [socket.chat.length]);

  return (
    <div className="flex flex-col gap-2">
      <div ref={listRef} className="flex max-h-60 flex-col gap-1 overflow-y-auto text-sm">
        {socket.chat.length === 0 && (
          <p className="text-ivory-dim/60">Personne n&rsquo;a encore rien dit.</p>
        )}
        {socket.chat.map((entry, i) => (
          <p key={i}>
            <span className="font-bold text-gold/90">
              {view.players[entry.seat]?.pseudo ?? "?"}
            </span>{" "}
            {entry.text}
          </p>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const text = draft.trim();
          if (text) {
            socket.sendChat(text);
            setDraft("");
          }
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={200}
          autoFocus
          placeholder="Écrire à la table"
          className="grow rounded-xl bg-black/30 px-3 py-2 text-sm ring-1 ring-white/15 placeholder:text-ivory-dim/50 focus:outline-2 focus:outline-gold"
        />
        <button
          type="submit"
          className="rounded-xl bg-felt-600 px-4 text-sm font-bold ring-1 ring-white/15 active:translate-y-0.5"
        >
          Envoyer
        </button>
      </form>
    </div>
  );
}

/* Les derniers messages, visibles en permanence ; un tap ouvre le chat complet. */
export function RecentChat({
  socket,
  view,
  onOpen,
  limit = 3,
}: {
  socket: RoomSocket;
  view: BaseRoomView;
  onOpen: () => void;
  limit?: number;
}) {
  const recent = socket.chat.slice(-limit);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-col gap-0.5 rounded-2xl bg-black/25 p-3 text-left text-sm ring-1 ring-white/10"
    >
      {recent.length === 0 && <span className="text-ivory-dim/60">Ouvrir le chat…</span>}
      {recent.map((entry, i) => (
        <span key={i} className="truncate">
          <span className="font-bold text-gold/90">
            {view.players[entry.seat]?.pseudo ?? "?"}
          </span>{" "}
          {entry.text}
        </span>
      ))}
    </button>
  );
}
