"use client";

import Lobby, { type BotChoice } from "@/components/Lobby";
import PlayingCard, { CardBackLabel } from "@/components/PlayingCard";
import TableFrame from "@/components/TableFrame";
import Table from "./Table";
import { GAME, MAX_SEATS } from "./meta";
import { useGoulagSocket, type GoulagSocket } from "./socket";
import type { RoomView } from "./types";

const BOT_CHOICES: BotChoice[] = [
  { id: "easy", hint: "Attaque, défend et charge au hasard. Pour apprendre." },
  {
    id: "normal",
    hint: "Répare sa défense, charge un peu, puis vise qui il peut tuer.",
  },
];

export default function TablePage() {
  return (
    <CardBackLabel.Provider value="G">
      <TableFrame<RoomView, GoulagSocket>
        game={GAME}
        useSocket={useGoulagSocket}
        rules={<Rules />}
        lobby={(socket, view) => (
          <Lobby
            socket={socket}
            view={view}
            maxSeats={MAX_SEATS}
            botChoices={BOT_CHOICES}
            onReady={(ready) => socket.setReady(ready)}
          >
            <p className="text-sm text-ivory-dim/80">
              Trois cartes chacun à l&rsquo;ouverture : les deux plus fortes
              sont tes vies, la plus faible ta défense. Le dernier survivant
              gagne.
            </p>
          </Lobby>
        )}
        table={(socket, view) => <Table socket={socket} view={view} />}
      />
    </CardBackLabel.Provider>
  );
}

function Rules() {
  return (
    <>
      <h2 className="mb-3 text-center text-lg font-extrabold">
        Les règles en bref
      </h2>
      <p className="mb-3 text-sm text-ivory-dim/85">
        Deux cartes de vie (leur somme), une carte de défense devant. À ton
        tour, annonce avant de piocher : Défense, Charge ou Attaque. Une attaque
        passe si elle dépasse la défense de la cible, et l&rsquo;écart lui coûte
        des vies. À zéro, on choisit une couleur : bonne carte, on revit ; sinon
        une dernière chance au milieu du paquet.
      </p>
      <ul className="flex flex-col gap-2 text-sm">
        <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-2">
          <PlayingCard card={{ value: 12, suit: "hearts" }} size="sm" />
          <span>
            Défense : la carte remplace un bouclier, le tien ou celui d&rsquo;un
            autre.
          </span>
        </li>
        <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-2">
          <PlayingCard faceDown size="sm" />
          <span>
            Charge : posée face cachée, elle s&rsquo;ajoutera à ta prochaine
            attaque. Deux maximum.
          </span>
        </li>
        <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-2">
          <PlayingCard card={{ value: 10, suit: "spades" }} size="sm" />
          <span>
            Attaque : carte + charges contre une défense. Touché, on perd ses
            charges.
          </span>
        </li>
        <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-2">
          <PlayingCard card={{ value: 14, suit: "diamonds" }} size="sm" />
          <span>
            Un seul As de vie : œil de faucon, tu vois la carte avant
            d&rsquo;annoncer.
          </span>
        </li>
      </ul>
    </>
  );
}
