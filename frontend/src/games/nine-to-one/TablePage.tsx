"use client";

import { LayoutGroup, motion } from "motion/react";
import { useState } from "react";
import Lobby, { type BotChoice } from "@/components/Lobby";
import PlayingCard, { CardBackLabel } from "@/components/PlayingCard";
import TableFrame from "@/components/TableFrame";
import type { CardT } from "@/lib/types";
import GameTable from "./GameTable";
import { GAME } from "./meta";
import { useNineToOneSocket, type NineToOneSocket } from "./socket";
import type { RoomView } from "./types";

const BOT_CHOICES: BotChoice[] = [
  { id: "easy", hint: "Joue au hasard, une carte à la fois. Pour apprendre." },
  {
    id: "normal",
    hint: "Économe : garde ses 2 et ses 10, pose ses multiples.",
  },
  {
    id: "hard",
    hint: "Réseau entraîné par auto-jeu : compte les cartes, enchaîne.",
  },
];

export default function TablePage() {
  return (
    <CardBackLabel.Provider value="9→1">
      <TableFrame<RoomView, NineToOneSocket>
        game={GAME}
        useSocket={useNineToOneSocket}
        rules={<Rules />}
        lobby={(socket, view) => (
          <Lobby
            socket={socket}
            view={view}
            maxSeats={5}
            botChoices={BOT_CHOICES}
            onReady={(ready) => socket.setReady(ready)}
          >
            <SwapSection socket={socket} view={view} />
          </Lobby>
        )}
        table={(socket, view) => <GameTable socket={socket} view={view} />}
      />
    </CardBackLabel.Provider>
  );
}

/* ----------------------------------------------------------------------- */
/* Lobby : l'échange initial main <-> cartes visibles                        */
/* ----------------------------------------------------------------------- */

function SwapSection({
  socket,
  view,
}: {
  socket: NineToOneSocket;
  view: RoomView;
}) {
  const you = view.players[view.your_seat];
  const [selectedHand, setSelectedHand] = useState<number | null>(null);
  const canSwap = !you.ready;

  return (
    <section className="flex flex-col gap-2">
      <p className="text-sm text-ivory-dim/80">
        {canSwap
          ? "Avant de te déclarer prêt, échange librement ta main avec tes cartes visibles."
          : "Tes cartes sont verrouillées, on attend les autres."}
      </p>
      <LayoutGroup id="swap">
        <div className="rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
          <p className="mb-1 text-xs text-ivory-dim/70">
            Cartes visibles sur la table
          </p>
          <div className="flex gap-2">
            {you.face_up.map((card, i) => (
              <SwapCard key={`${card.value}-${card.suit}`} card={card}>
                <PlayingCard
                  card={card}
                  size="md"
                  disabled={!canSwap}
                  highlighted={canSwap && selectedHand !== null}
                  onClick={
                    canSwap
                      ? () => {
                          if (selectedHand !== null) {
                            socket.swap(selectedHand, i);
                            setSelectedHand(null);
                          }
                        }
                      : undefined
                  }
                />
              </SwapCard>
            ))}
          </div>
          <p className="mb-1 mt-3 text-xs text-ivory-dim/70">Ta main</p>
          <div className="flex gap-2">
            {(you.hand ?? []).map((card, i) => (
              <SwapCard key={`${card.value}-${card.suit}`} card={card}>
                <PlayingCard
                  card={card}
                  size="md"
                  disabled={!canSwap}
                  selected={selectedHand === i}
                  onClick={
                    canSwap
                      ? () => setSelectedHand(selectedHand === i ? null : i)
                      : undefined
                  }
                />
              </SwapCard>
            ))}
          </div>
        </div>
      </LayoutGroup>
    </section>
  );
}

/* Une carte de l'échange initial : même `layoutId` dans les deux rangées, donc quand
   le serveur renvoie la main et les visibles échangées, chaque carte glisse de son
   ancienne place à la nouvelle (et la main re-triée se réordonne en douceur). */
function SwapCard({
  card,
  children,
}: {
  card: CardT;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      layout
      layoutId={`swap-${card.value}-${card.suit}`}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
    >
      {children}
    </motion.div>
  );
}

/* Rappel des règles, surtout les pouvoirs des cartes spéciales. */
function Rules() {
  const powers: { card: CardT; text: string }[] = [
    {
      card: { value: 2, suit: "spades" },
      text: "Se pose sur tout. Le joueur suivant est libre.",
    },
    {
      card: { value: 7, suit: "diamonds" },
      text: "Tu choisis : le suivant joue au-dessus ou en dessous de 7.",
    },
    {
      card: { value: 9, suit: "clubs" },
      text: "Le suivant doit jouer 9 ou moins.",
    },
    {
      card: { value: 10, suit: "hearts" },
      text: "Coupe le tas : tout part à la défausse et tu rejoues. Interdit quand il faut jouer en dessous.",
    },
  ];
  return (
    <>
      <h2 className="mb-3 text-center text-lg font-extrabold">
        Les règles en bref
      </h2>
      <p className="mb-3 text-sm text-ivory-dim/85">
        Chacun pose une carte égale ou plus forte que la précédente, et repioche
        à 3 cartes tant que la pioche dure. Bloqué ? Tu ramasses tout le tas. 4
        cartes identiques d&rsquo;affilée coupent le tas. Main vidée : tu joues
        tes cartes visibles, puis tes cachées à l&rsquo;aveugle. Le dernier avec
        des cartes perd.
      </p>
      <ul className="flex flex-col gap-2">
        {powers.map(({ card, text }) => (
          <li
            key={card.value}
            className="flex items-center gap-3 rounded-2xl bg-black/25 p-2"
          >
            <PlayingCard card={card} size="sm" />
            <span className="text-sm">{text}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
