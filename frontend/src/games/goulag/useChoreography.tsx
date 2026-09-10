"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import FlipCard from "@/components/FlipCard";
import { spawnFlight } from "@/components/FlightLayer";
import PlayingCard from "@/components/PlayingCard";
import { anchorCenter } from "@/lib/anchors";
import { sfx, vibrate } from "@/lib/sound";
import type { CardT, GameEvent } from "@/lib/types";
import { SUIT_GLYPH, face } from "./cards";
import type { GoulagSocket } from "./socket";
import type { RoomView } from "./types";

/* La chorégraphie de la table : les événements du serveur sont rejoués dans l'ordre,
   avec des vols de cartes entre les ancres (pioche, défausse, bouclier, vies, charges
   de chaque siège), des effets sur les sièges (secousse, éclat, chiffre de dégâts) et
   des sons. La vue affichée (`shown`) ne bascule sur la nouvelle qu'à la fin de la
   séquence : les cartes ne se téléportent jamais avant que l'histoire soit racontée.

   Ancres attendues (voir Table.tsx) : "deck", "discard", `shield-${seat}`,
   `lives-${seat}`, `charges-${seat}`, `seat-${seat}`. */

export type SeatFx = {
  shake: number; // incrémenté à chaque secousse (clé d'animation)
  flash: "hit" | "block" | "heal" | "death" | null;
  popup: { id: number; text: string; tone: "damage" | "block" | "info" } | null;
};

export type CenterFx = {
  /* Une carte retournée au centre (résurrection), avec son verdict. */
  card: CardT | null;
  tone: "reveal" | "success" | "fail";
  big: boolean;
  /* La pioche coupée en deux (seconde chance). */
  split: boolean;
};

export type Fx = { seats: Record<number, SeatFx>; center: CenterFx };

const EMPTY_SEAT: SeatFx = { shake: 0, flash: null, popup: null };
const EMPTY_CENTER: CenterFx = {
  card: null,
  tone: "reveal",
  big: false,
  split: false,
};

const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

let popupId = 0;

export function useChoreography(
  socket: GoulagSocket,
  view: RoomView,
): { shown: RoomView; fx: Fx } {
  const [shown, setShown] = useState<RoomView>(view);
  const [fx, setFx] = useState<Fx>({ seats: {}, center: EMPTY_CENTER });
  const shownRef = useRef(view);
  const latestRef = useRef(view);
  const busyRef = useRef(false);
  const queueRef = useRef<{ events: GameEvent[]; next: RoomView }[]>([]);

  /* `bump` : une secousse de plus (le compteur sert de clé d'animation). */
  const seatFx = useCallback(
    (seat: number, patch: Partial<SeatFx>, bump = false) => {
      setFx((prev) => {
        const current = prev.seats[seat] ?? EMPTY_SEAT;
        return {
          ...prev,
          seats: {
            ...prev.seats,
            [seat]: {
              ...current,
              ...patch,
              shake: current.shake + (bump ? 1 : 0),
            },
          },
        };
      });
    },
    [],
  );
  const centerFx = useCallback((patch: Partial<CenterFx>) => {
    setFx((prev) => ({ ...prev, center: { ...prev.center, ...patch } }));
  }, []);

  const { onEvents } = socket;
  const commit = useCallback((next: RoomView) => {
    shownRef.current = next;
    setShown(next);
  }, []);

  /* Une vue sans événement (reconnexion, arrivée d'un joueur) : on l'applique tout de
     suite si rien ne joue, sinon elle sera rattrapée à la fin de la séquence. */
  useEffect(() => {
    latestRef.current = view;
    if (!busyRef.current) commit(view);
  }, [view, commit]);

  useEffect(() => {
    onEvents((events, next) => {
      queueRef.current.push({ events, next });
      if (!busyRef.current) void drain();
    });

    async function drain() {
      busyRef.current = true;
      try {
        while (queueRef.current.length) {
          const { events, next } = queueRef.current.shift()!;
          await play(events, shownRef.current, next);
          commit(next);
        }
      } finally {
        busyRef.current = false;
        // Une vue silencieuse a pu arriver pendant la séquence.
        if (latestRef.current !== shownRef.current) commit(latestRef.current);
      }
    }

    async function play(
      events: GameEvent[],
      before: RoomView,
      after: RoomView,
    ) {
      const me = before.your_seat;
      // Les cartes volent à la taille de leur destination : petites vers un adversaire.
      const sizeFor = (seat: number): "ms" | "md" =>
        seat === me ? "md" : "ms";
      for (const e of events) {
        switch (e.type) {
          case "charged": {
            const seat = e.player as number;
            sfx.pickup();
            spawnFlight({
              from: "deck",
              to: `charges-${seat}`,
              content: <PlayingCard faceDown size={sizeFor(seat)} />,
              duration: 0.5,
            });
            await wait(520);
            break;
          }
          case "revealed": {
            const seat = e.player as number;
            const target = e.target as number;
            const card = face(e.card as CardT);
            const attack = e.action === "attack";
            // Les charges jouées : leurs valeurs arrivent dans l'événement d'attaque qui
            // suit ; elles se retournent sur place en même temps que la carte piochée.
            const attackEvent = attack
              ? events.find((x) => x.type === "attacked" && x.player === seat)
              : undefined;
            const charges = (
              (attackEvent?.charges as CardT[] | undefined) ?? []
            ).map(face);
            sfx.flip();
            spawnFlight({
              from: "deck",
              to: "deck",
              content: <FlipCard card={card} size="md" duration={0.45} />,
              duration: 0.55,
              still: true,
            });
            charges.forEach((c, i) =>
              spawnFlight({
                from: `charges-${seat}`,
                to: `charges-${seat}`,
                content: (
                  <FlipCard
                    card={c}
                    size={sizeFor(seat)}
                    duration={0.45}
                    delay={0.1 * i}
                  />
                ),
                duration: 0.55 + 0.1 * i,
                still: true,
              }),
            );
            await wait(560 + 100 * charges.length);
            sfx.pickup();
            spawnFlight({
              from: "deck",
              to: `shield-${target}`,
              content: <PlayingCard card={card} size={sizeFor(target)} />,
              duration: 0.45,
            });
            charges.forEach((c, i) =>
              spawnFlight({
                from: `charges-${seat}`,
                to: `shield-${target}`,
                content: <PlayingCard card={c} size={sizeFor(target)} />,
                delay: 0.08 * (i + 1),
                duration: 0.45,
              }),
            );
            await wait(470 + 80 * charges.length);
            break;
          }
          case "attacked": {
            const target = e.target as number;
            const damage = e.damage as number;
            const card = face(e.card as CardT);
            if (damage > 0) {
              sfx.hit();
              vibrate([30, 40, 60]);
              seatFx(
                target,
                {
                  flash: "hit",
                  popup: { id: ++popupId, text: `−${damage}`, tone: "damage" },
                },
                true,
              );
            } else {
              sfx.block();
              vibrate(20);
              seatFx(
                target,
                {
                  flash: "block",
                  popup: { id: ++popupId, text: "Bloqué", tone: "block" },
                },
                true,
              );
            }
            setTimeout(() => seatFx(target, { flash: null }), 450);
            setTimeout(() => seatFx(target, { popup: null }), 1400);
            // Les cartes jouées glissent à la défausse.
            const played = [card, ...((e.charges as CardT[]) ?? []).map(face)];
            played.forEach((c, i) =>
              spawnFlight({
                from: `shield-${target}`,
                to: "discard",
                content: <PlayingCard card={c} size="ms" />,
                delay: 0.3 + i * 0.07,
                duration: 0.4,
              }),
            );
            await wait(damage > 0 ? 650 : 550);
            break;
          }
          case "charges_lost": {
            const seat = e.player as number;
            const count = before.players[seat]?.charges ?? 0;
            for (let i = 0; i < count; i++) {
              spawnFlight({
                from: `charges-${seat}`,
                to: "discard",
                content: <PlayingCard faceDown size="ms" />,
                delay: i * 0.08,
                duration: 0.45,
              });
            }
            await wait(320);
            break;
          }
          case "lives_updated": {
            const seat = e.player as number;
            const removed = (e.removed as CardT[]).map(face);
            const added = (e.added as CardT[]).map(face);
            removed.forEach((c, i) =>
              spawnFlight({
                from: `lives-${seat}`,
                to: "discard",
                content: <PlayingCard card={c} size="ms" />,
                delay: i * 0.08,
                duration: 0.4,
              }),
            );
            added.forEach((c, i) =>
              spawnFlight({
                from: "discard",
                to: `lives-${seat}`,
                content: <PlayingCard card={c} size={sizeFor(seat)} />,
                delay: 0.3 + i * 0.08,
                duration: 0.45,
              }),
            );
            if (added.length) {
              setTimeout(() => sfx.play(), 700);
            }
            await wait(removed.length || added.length ? 800 : 0);
            break;
          }
          case "defense_changed": {
            const target = e.target as number;
            const old = e.old as CardT | null;
            if (old) {
              spawnFlight({
                from: `shield-${target}`,
                to: "discard",
                content: <PlayingCard card={face(old)} size="ms" />,
                duration: 0.4,
              });
            }
            sfx.play();
            seatFx(target, {
              flash: "heal",
              popup: {
                id: ++popupId,
                text: `Bouclier ${(e.card as CardT).value}`,
                tone: "info",
              },
            });
            setTimeout(() => seatFx(target, { flash: null }), 450);
            setTimeout(() => seatFx(target, { popup: null }), 1300);
            await wait(450);
            break;
          }
          case "died": {
            const seat = e.player as number;
            const lives = (before.players[seat]?.lives ?? []).map(face);
            sfx.thud();
            vibrate([60, 40, 80]);
            seatFx(
              seat,
              {
                flash: "death",
                popup: { id: ++popupId, text: "À terre", tone: "damage" },
              },
              true,
            );
            lives.forEach((c, i) =>
              spawnFlight({
                from: `lives-${seat}`,
                to: "discard",
                content: <PlayingCard card={c} size={sizeFor(seat)} />,
                delay: 0.2 + i * 0.1,
                duration: 0.5,
              }),
            );
            setTimeout(() => seatFx(seat, { flash: null }), 600);
            setTimeout(() => seatFx(seat, { popup: null }), 1500);
            await wait(900);
            break;
          }
          case "suit_chosen": {
            const seat = e.player as number;
            const suit = e.suit as CardT["suit"];
            seatFx(seat, {
              popup: { id: ++popupId, text: SUIT_GLYPH[suit], tone: "info" },
            });
            setTimeout(() => seatFx(seat, { popup: null }), 1400);
            await wait(500);
            break;
          }
          case "revival_flip": {
            const seat = e.player as number;
            const attempt = e.attempt as number;
            const card = face(e.card as CardT);
            const success = e.success as boolean;
            if (attempt === 2) {
              // On coupe le paquet : les deux moitiés s'écartent, la carte du milieu sort.
              centerFx({ split: true });
              sfx.shuffle();
              await wait(650);
            }
            sfx.flip();
            centerFx({ card, tone: "reveal", big: true, split: false });
            await wait(900);
            centerFx({ tone: success ? "success" : "fail" });
            if (success) {
              sfx.bell();
              vibrate([20, 30, 20]);
            } else {
              sfx.nope();
            }
            await wait(700);
            centerFx({ card: null, big: false });
            spawnFlight({
              from: "deck",
              to: success ? `lives-${seat}` : "discard",
              content: (
                <PlayingCard
                  card={card}
                  size={success ? sizeFor(seat) : "sm"}
                />
              ),
              duration: 0.5,
            });
            await wait(520);
            break;
          }
          case "revived": {
            const seat = e.player as number;
            seatFx(seat, {
              flash: "heal",
              popup: { id: ++popupId, text: "Revient !", tone: "info" },
            });
            setTimeout(() => seatFx(seat, { flash: null }), 600);
            setTimeout(() => seatFx(seat, { popup: null }), 1400);
            await wait(300);
            break;
          }
          case "eliminated": {
            const seat = e.player as number;
            const defense = e.defense as CardT | null;
            if (defense) {
              // Son bouclier retourne en jeu : il glisse à la défausse.
              spawnFlight({
                from: `shield-${seat}`,
                to: "discard",
                content: <PlayingCard card={face(defense)} size="ms" />,
                delay: 0.2,
                duration: 0.5,
              });
            }
            seatFx(seat, {
              flash: "death",
              popup: { id: ++popupId, text: "Éliminé", tone: "damage" },
            });
            setTimeout(() => seatFx(seat, { flash: null }), 800);
            setTimeout(() => seatFx(seat, { popup: null }), 1600);
            if (seat === me) sfx.lose();
            await wait(500);
            break;
          }
          case "deck_reshuffled": {
            sfx.shuffle();
            for (let i = 0; i < 4; i++) {
              spawnFlight({
                from: "discard",
                to: "deck",
                content: <PlayingCard faceDown size="md" />,
                delay: i * 0.09,
                duration: 0.4,
              });
            }
            await wait(700);
            break;
          }
          case "turn": {
            if (e.player === me && after.status === "playing") sfx.yourTurn();
            break;
          }
          case "game_over": {
            const mine = after.players[me]?.finish_rank;
            if (mine === 1) sfx.win();
            await wait(600);
            break;
          }
          default:
            break;
        }
      }
    }
  }, [onEvents, commit, seatFx, centerFx]);

  return { shown, fx };
}

/* Un siège est-il visible à l'écran ? (les vols vers une ancre absente sont ignorés) */
export function hasAnchor(key: string): boolean {
  return anchorCenter(key) !== null;
}
