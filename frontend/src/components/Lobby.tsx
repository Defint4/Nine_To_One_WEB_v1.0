"use client";

import { useState } from "react";
import Avatar from "@/components/Avatar";
import ChatPanel, { RecentChat } from "@/components/ChatPanel";
import { Sheet } from "@/components/Sheet";
import { EMOTES } from "@/lib/emotes";
import { BOT_LABELS, type BasePlayerView, type BaseRoomView, type BotDifficulty } from "@/lib/types";
import type { RoomSocket } from "@/lib/useRoomSocket";

/* Le lobby commun à tous les jeux : sièges, bots, temps par tour, prêt, chat.
   Chaque jeu glisse sa propre section entre le timer et le bouton « prêt »
   (Nine to One : l'échange initial). */

export type LobbyPlayer = BasePlayerView & { ready: boolean };
export type LobbyView = Omit<BaseRoomView, "players"> & { players: LobbyPlayer[] };

export type BotChoice = { id: BotDifficulty; hint: string };

export default function Lobby({
  socket,
  view,
  maxSeats,
  botChoices,
  onReady,
  children,
}: {
  socket: RoomSocket<BaseRoomView>;
  view: LobbyView;
  maxSeats: number;
  botChoices: BotChoice[];
  onReady: (ready: boolean) => void;
  children?: React.ReactNode;
}) {
  const you = view.players[view.your_seat];
  const [botSheetOpen, setBotSheetOpen] = useState(false);
  const isCreator = view.your_seat === 0;
  const free = maxSeats - view.players.length;

  return (
    <div className="flex min-h-full flex-col gap-5">
      <header className="pr-12">
        <h1 className="text-2xl font-extrabold">
          Table <span className="tracking-widest text-gold">{view.code}</span>
        </h1>
        <p className="text-sm text-ivory-dim/80">
          Partage ce code — la partie démarre quand tout le monde est prêt.
        </p>
      </header>

      <ul className="flex flex-col gap-2">
        {view.players.map((player) => (
          <SeatRow
            key={player.seat}
            player={player}
            you={player.seat === view.your_seat}
            onRemove={isCreator && player.bot ? () => socket.removeBot(player.seat) : undefined}
          />
        ))}
        {free > 0 && (
          <li className="flex items-center rounded-2xl border border-dashed border-ivory-dim/30 py-1.5 pl-3 pr-1.5 text-sm text-ivory-dim/60">
            <span className="grow text-center">
              {free} place{free > 1 ? "s" : ""} libre{free > 1 ? "s" : ""}
            </span>
            {botChoices.length > 0 && (
              <button
                type="button"
                aria-label="Ajouter un bot"
                disabled={!isCreator}
                onClick={() => setBotSheetOpen(true)}
                className={`flex items-center gap-1 rounded-full px-2.5 py-1.5 font-bold ring-1 ring-white/15 ${
                  isCreator ? "bg-white/10 text-ivory active:scale-95" : "bg-white/5 text-ivory-dim/40"
                }`}
              >
                <span className="text-base leading-none">+</span>
                <RobotIcon />
              </button>
            )}
          </li>
        )}
      </ul>

      {botSheetOpen && (
        <BotSheet
          choices={botChoices}
          onPick={(difficulty) => {
            socket.addBot(difficulty);
            setBotSheetOpen(false);
          }}
          onClose={() => setBotSheetOpen(false)}
        />
      )}

      <section className="flex items-center gap-2 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
        <span className="grow text-sm font-bold">Temps par tour</span>
        {[0, 30, 60].map((seconds) => (
          <button
            key={seconds}
            type="button"
            disabled={!isCreator}
            onClick={() => socket.setTurnSeconds(seconds)}
            className={`rounded-full px-3 py-1 text-sm font-bold ${
              view.turn_seconds === seconds ? "bg-gold text-ink" : "bg-white/10 text-ivory-dim/70"
            } ${isCreator ? "active:scale-95" : "cursor-default"}`}
          >
            {seconds === 0 ? "Sans" : `${seconds} s`}
          </button>
        ))}
      </section>

      {children}

      <button
        type="button"
        onClick={() => onReady(!you.ready)}
        className={`rounded-2xl py-4 text-lg font-extrabold shadow-card active:translate-y-0.5 ${
          you.ready ? "bg-felt-600 text-ivory ring-1 ring-white/15" : "bg-gold text-ink"
        }`}
      >
        {you.ready ? "Je ne suis plus prêt" : "Je suis prêt"}
      </button>

      <LobbyChat socket={socket} view={view} />
    </div>
  );
}

function SeatRow({
  player,
  you,
  onRemove,
}: {
  player: LobbyPlayer;
  you: boolean;
  onRemove?: () => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
      <Avatar id={player.avatar} dimmed={!player.connected} />
      <span className={`min-w-0 font-bold ${player.connected ? "" : "text-ivory-dim/50"}`}>
        <span className="block truncate">
          {player.pseudo}
          {you && <span className="text-ivory-dim/60"> (toi)</span>}
        </span>
        {player.bot && (
          <span className="flex items-center gap-1 text-xs font-semibold text-ivory-dim/70">
            <RobotIcon className="size-3.5" /> Bot {BOT_LABELS[player.bot].toLowerCase()}
          </span>
        )}
      </span>
      <span
        className={`ml-auto shrink-0 rounded-full px-3 py-1 text-sm font-bold ${
          player.ready ? "bg-gold text-ink" : "bg-white/10 text-ivory-dim/70"
        }`}
      >
        {player.ready ? "Prêt" : "Pas prêt"}
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Retirer ${player.pseudo}`}
          className="-mr-1 shrink-0 rounded-full p-1.5 text-ivory-dim/70 ring-1 ring-white/15 active:scale-90"
        >
          <svg viewBox="0 0 24 24" className="size-4 fill-none stroke-current stroke-[2.5]">
            <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      )}
    </li>
  );
}

/* Choix de la difficulté d'un bot à ajouter (créateur seulement). */
function BotSheet({
  choices,
  onPick,
  onClose,
}: {
  choices: BotChoice[];
  onPick: (difficulty: BotDifficulty) => void;
  onClose: () => void;
}) {
  return (
    <Sheet onClose={onClose}>
      <h2 className="mb-1 flex items-center justify-center gap-2 text-center text-lg font-extrabold">
        <RobotIcon className="size-5" /> Ajouter un bot
      </h2>
      <p className="mb-4 text-center text-sm text-ivory-dim/80">
        Il se met prêt tout seul et suit la revanche.
      </p>
      <div className="flex flex-col gap-2">
        {choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            onClick={() => onPick(choice.id)}
            className="flex flex-col rounded-2xl bg-black/25 p-4 text-left ring-1 ring-white/10 active:translate-y-0.5"
          >
            <span className="font-extrabold text-gold">{BOT_LABELS[choice.id]}</span>
            <span className="text-sm text-ivory-dim/80">{choice.hint}</span>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

export function RobotIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} fill-none stroke-current stroke-2`} aria-hidden>
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path strokeLinecap="round" d="M12 8V4M9 4h6M2 13v3M22 13v3M9 17h6" />
      <circle cx="9" cy="13" r="1.2" className="fill-current" />
      <circle cx="15" cy="13" r="1.2" className="fill-current" />
    </svg>
  );
}

function LobbyChat({ socket, view }: { socket: RoomSocket<BaseRoomView>; view: LobbyView }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="mt-auto flex flex-col gap-2">
      <RecentChat socket={socket} view={view} onOpen={() => setOpen(true)} />
      <div className="flex gap-1">
        {Object.entries(EMOTES).map(([id, emoji]) => (
          <button
            key={id}
            type="button"
            onClick={() => socket.sendEmote(id)}
            className="rounded-full bg-black/25 px-2 py-1 text-lg ring-1 ring-white/10 active:scale-90"
            aria-label={`Envoyer ${emoji}`}
          >
            {emoji}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-1 text-sm text-ivory-dim/70">
          {socket.emotes.map((e) => (
            <span key={e.id}>
              <span className="font-bold text-gold/90">{view.players[e.seat]?.pseudo ?? "?"}</span>{" "}
              {EMOTES[e.emote] ?? e.emote}
            </span>
          ))}
        </span>
      </div>
      {open && (
        <Sheet onClose={() => setOpen(false)}>
          <ChatPanel socket={socket} view={view} />
        </Sheet>
      )}
    </section>
  );
}
