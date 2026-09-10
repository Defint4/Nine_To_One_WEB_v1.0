"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { spawnFlight } from "@/components/FlightLayer";
import { burst, screenFx, shockwave, tracer } from "@/components/FxLayer";
import PlayingCard from "@/components/PlayingCard";
import { sfx, vibrate } from "@/lib/sound";
import type { CardT, GameEvent } from "@/lib/types";
import { SUIT_GLYPH, face } from "./cards";
import type { GoulagSocket } from "./socket";
import type { PlayerView, RoomView } from "./types";

/* La chorégraphie de la table : les événements du serveur sont rejoués dans l'ordre,
   avec des vols de cartes entre les ancres (pioche, défausse, scène, bouclier, vies,
   charges de chaque siège), des effets sur les sièges (secousse, éclat, mot qui
   claque), des effets d'écran (tir, étincelles, onde de choc, éclair, vignette) et des
   sons. La vue affichée (`shown`) ne bascule sur la nouvelle qu'à la fin de la
   séquence : les cartes ne se téléportent jamais avant que l'histoire soit racontée.

   Chaque moment suit le même rythme : anticipation, coup, temps mort pour lire, puis
   résolution. Rien ne se joue en dessous de la taille où on peut lire une carte : la
   carte piochée se retourne sur la scène, au centre de la table, et y reste.

   Ancres attendues (voir Table.tsx) : "deck", "discard", "stage", `shield-${seat}`,
   `lives-${seat}`, `charges-${seat}`, `seat-${seat}`. */

export type FlashKind = "hit" | "block" | "heal" | "death";
export type PopupTone = "damage" | "block" | "info" | "attack" | "charge" | "defend";

export type SeatFx = {
  shake: number; // incrémenté à chaque secousse
  flash: { id: number; kind: FlashKind } | null;
  popup: { id: number; text: string; tone: PopupTone; big?: boolean } | null;
};

/* La scène : les cartes retournées au centre de la table (carte piochée et charges,
   ou carte de résurrection), avec un verdict et une légende. */
export type StageFx = {
  id: number;
  cards: CardT[];
  tone: "reveal" | "success" | "fail";
  caption: string | null;
  spotlight: boolean;
};

export type CenterFx = {
  stage: StageFx | null;
  /* La pioche coupée en deux (seconde chance). */
  split: boolean;
};

export type Fx = {
  seats: Record<number, SeatFx>;
  center: CenterFx;
  tableShake: number;
};

const EMPTY_SEAT: SeatFx = { shake: 0, flash: null, popup: null };
const EMPTY_CENTER: CenterFx = { stage: null, split: false };

/* Le tempo, en millisecondes. */
const T = {
  fly: 500, // un vol de carte
  flip: 500, // un retournement
  read: 950, // le temps de lire une carte retournée
  verdict: 800, // le temps d'encaisser un verdict (touché, bloqué, revit…)
  beat: 140, // le micro-arrêt au moment d'un impact
};

const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

let fxId = 0;

const SPARK_HIT = ["#ffd166", "#ff8c42", "#ff4d3d", "#fff1c1"];
const SPARK_BLOCK = ["#ffffff", "#e5b54a", "#fff7d6", "#b9d8ff"];
const SPARK_GOLD = ["#e5b54a", "#fff1c1", "#ffffff", "#c4923a"];
const DUST = ["#2a2a2a", "#4a4a4a", "#1a1a1a"];

export function useChoreography(
  socket: GoulagSocket,
  view: RoomView,
): { shown: RoomView; fx: Fx } {
  const [shown, setShown] = useState<RoomView>(view);
  const [fx, setFx] = useState<Fx>({
    seats: {},
    center: EMPTY_CENTER,
    tableShake: 0,
  });
  const shownRef = useRef(view);
  const latestRef = useRef(view);
  const busyRef = useRef(false);
  const queueRef = useRef<{ events: GameEvent[]; next: RoomView }[]>([]);

  const patchSeat = useCallback(
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

  /* Un éclat sur un siège, retiré après `ms` seulement s'il est encore le courant :
     un effet plus récent n'est jamais effacé par le minuteur d'un plus ancien. */
  const flash = useCallback(
    (seat: number, kind: FlashKind, ms: number, bump = false) => {
      const id = ++fxId;
      patchSeat(seat, { flash: { id, kind } }, bump);
      setTimeout(() => {
        setFx((prev) => {
          const current = prev.seats[seat];
          if (!current || current.flash?.id !== id) return prev;
          return {
            ...prev,
            seats: { ...prev.seats, [seat]: { ...current, flash: null } },
          };
        });
      }, ms);
    },
    [patchSeat],
  );

  const popup = useCallback(
    (
      seat: number,
      text: string,
      tone: PopupTone,
      ms: number,
      big = false,
    ) => {
      const id = ++fxId;
      patchSeat(seat, { popup: { id, text, tone, big } });
      setTimeout(() => {
        setFx((prev) => {
          const current = prev.seats[seat];
          if (!current || current.popup?.id !== id) return prev;
          return {
            ...prev,
            seats: { ...prev.seats, [seat]: { ...current, popup: null } },
          };
        });
      }, ms);
    },
    [patchSeat],
  );

  const center = useCallback((patch: Partial<CenterFx>) => {
    setFx((prev) => ({ ...prev, center: { ...prev.center, ...patch } }));
  }, []);
  const stage = useCallback(
    (patch: Partial<StageFx> | null) => {
      setFx((prev) => ({
        ...prev,
        center: {
          ...prev.center,
          stage:
            patch === null
              ? null
              : {
                  id: prev.center.stage?.id ?? ++fxId,
                  cards: [],
                  tone: "reveal",
                  caption: null,
                  spotlight: false,
                  ...prev.center.stage,
                  ...patch,
                },
        },
      }));
    },
    [],
  );
  const shakeTable = useCallback(() => {
    setFx((prev) => ({ ...prev, tableShake: prev.tableShake + 1 }));
  }, []);

  const { onEvents } = socket;
  const commit = useCallback((next: RoomView) => {
    shownRef.current = next;
    setShown(next);
  }, []);

  /* Retouche la vue affichée en cours de séquence : la carte qui vient de se poser
     remplace tout de suite celle du tapis, sans attendre la fin de l'histoire. */
  const patchShown = useCallback(
    (seat: number, patch: Partial<PlayerView>) => {
      const current = shownRef.current;
      commit({
        ...current,
        players: current.players.map((p) =>
          p.seat === seat ? { ...p, ...patch } : p,
        ),
      });
    },
    [commit],
  );

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

    /* Un vol de carte, plein, qui se soulève et tourne un peu. */
    function fly(
      from: string,
      to: string,
      card: CardT | null,
      options: {
        size?: "sm" | "ms" | "md" | "lg";
        delay?: number;
        spin?: number;
      } = {},
    ) {
      spawnFlight({
        from,
        to,
        content: card ? (
          <PlayingCard card={card} size={options.size ?? "ms"} />
        ) : (
          <PlayingCard faceDown size={options.size ?? "ms"} />
        ),
        delay: options.delay ?? 0,
        duration: T.fly / 1000,
        solid: true,
        arc: 36,
        spin: options.spin ?? (Math.random() < 0.5 ? -9 : 9),
      });
    }

    async function play(
      events: GameEvent[],
      before: RoomView,
      after: RoomView,
    ) {
      const me = before.your_seat;
      const name = (seat: number) => before.players[seat]?.pseudo ?? "";
      const seatNow = (seat: number) => shownRef.current.players[seat];
      // Les boucliers déjà remplacés sur le tapis pendant la révélation.
      const shieldDone = new Set<number>();
      // Les cartes volent à la taille de leur destination : petites vers un adversaire.
      const sizeFor = (seat: number): "ms" | "md" =>
        seat === me ? "md" : "ms";

      for (const e of events) {
        switch (e.type) {
          case "announced": {
            // Le mot claque au-dessus du joueur avant même qu'il vise : tout le monde
            // sait ce qui se prépare.
            const seat = e.player as number;
            const action = e.action as "attack" | "defend" | "charge";
            const label = {
              attack: "Attaque !",
              defend: "Défense",
              charge: "Charge",
            }[action];
            if (action === "attack") {
              sfx.cut();
              vibrate(15);
            } else sfx.pickup();
            popup(seat, label, action, 1400, true);
            await wait(700);
            break;
          }
          case "charged": {
            const seat = e.player as number;
            sfx.pickup();
            fly("deck", `charges-${seat}`, null, { size: sizeFor(seat) });
            await wait(T.fly - 40);
            patchShown(seat, { charges: (seatNow(seat)?.charges ?? 0) + 1 });
            await wait(190);
            break;
          }
          case "revealed": {
            const seat = e.player as number;
            const target = e.target as number;
            const card = face(e.card as CardT);
            const attack = e.action === "attack";
            // Les charges jouées : leurs valeurs arrivent dans l'événement d'attaque qui
            // suit ; elles rejoignent la scène et se retournent avec la carte piochée.
            const attackEvent = attack
              ? events.find((x) => x.type === "attacked" && x.player === seat)
              : undefined;
            const charges = (
              (attackEvent?.charges as CardT[] | undefined) ?? []
            ).map(face);

            // 1. La carte quitte la pioche, face cachée, et les charges quittent le tapis.
            // Elle arrive à la taille de la scène, sans rotation : la scène prend le
            // relais au même endroit, on ne voit pas la couture.
            sfx.pickup();
            fly("deck", "stage", null, { size: "lg", spin: 0 });
            charges.forEach((_, i) =>
              fly(`charges-${seat}`, "stage", null, {
                size: "md",
                delay: 0.08 * (i + 1),
                spin: -6,
              }),
            );
            await wait(T.fly + 80 * charges.length);

            // 2. Sur la scène, tout se retourne, et on laisse le temps de lire.
            sfx.flip();
            stage({
              cards: [card, ...charges],
              tone: "reveal",
              caption: null,
              spotlight: false,
            });
            await wait(T.flip);
            if (attack) {
              const total = attackEvent?.total as number | undefined;
              const defense = attackEvent?.defense as number | undefined;
              stage({
                caption:
                  total !== undefined && defense !== undefined
                    ? `${total} contre ${defense} — ${name(target)}`
                    : `Sur ${name(target)}`,
              });
            } else {
              stage({
                caption:
                  target === seat
                    ? "Nouveau bouclier"
                    : `Bouclier pour ${name(target)}`,
              });
            }
            await wait(T.read);

            // 3. Les cartes partent vers la cible ; une attaque file comme un tir.
            stage(null);
            sfx.pickup();
            const all = [card, ...charges];
            all.forEach((c, i) =>
              fly("stage", `shield-${target}`, c, {
                size: sizeFor(target),
                delay: 0.07 * i,
                spin: attack ? 16 : 6,
              }),
            );
            if (!attack) {
              // L'ancien bouclier s'en va quand le nouveau arrive, et à l'atterrissage
              // le tapis montre déjà la nouvelle carte : rien ne traîne.
              const old = seatNow(target)?.defense ?? null;
              if (old) {
                fly(`shield-${target}`, "discard", face(old), {
                  delay: 0.25,
                  spin: -14,
                });
              }
              const raw = e.card as CardT;
              setTimeout(() => patchShown(target, { defense: raw }), T.fly - 40);
              shieldDone.add(target);
            }
            if (attack) {
              tracer("stage", `lives-${target}`, {
                duration: T.fly / 1000,
                color: "rgba(255,210,120,0.95)",
              });
            }
            await wait(T.fly + 70 * charges.length);
            break;
          }
          case "attacked": {
            const target = e.target as number;
            const damage = e.damage as number;
            const card = face(e.card as CardT);
            // Le micro-arrêt : une fraction de seconde où rien ne bouge, puis le coup.
            await wait(T.beat);
            if (damage > 0) {
              sfx.hit();
              vibrate([30, 40, 60]);
              shakeTable();
              flash(target, "hit", 700, true);
              screenFx("hit");
              shockwave(`lives-${target}`, {
                color: "rgba(255,120,80,0.9)",
                radius: 110,
              });
              burst(`lives-${target}`, {
                colors: SPARK_HIT,
                count: 34,
                speed: 380,
                size: 3.2,
                life: 0.75,
              });
              burst(`lives-${target}`, {
                colors: DUST,
                count: 12,
                speed: 140,
                size: 5,
                life: 0.9,
                gravity: 300,
                streak: false,
              });
              await wait(180);
              popup(target, `−${damage}`, "damage", 1600, true);
            } else {
              sfx.block();
              vibrate(20);
              flash(target, "block", 600, true);
              shockwave(`shield-${target}`, {
                color: "rgba(229,181,74,0.95)",
                radius: 70,
                width: 4,
              });
              burst(`shield-${target}`, {
                colors: SPARK_BLOCK,
                count: 28,
                speed: 420,
                size: 2.4,
                life: 0.55,
                gravity: 600,
              });
              await wait(180);
              popup(target, "Bloqué", "block", 1400, true);
            }
            await wait(T.verdict);
            // Les cartes jouées glissent à la défausse.
            const played = [card, ...((e.charges as CardT[]) ?? []).map(face)];
            played.forEach((c, i) =>
              fly(`shield-${target}`, "discard", c, { delay: i * 0.08 }),
            );
            await wait(T.fly + 80 * (played.length - 1));
            break;
          }
          case "charges_lost": {
            const seat = e.player as number;
            const count = seatNow(seat)?.charges ?? 0;
            if (count) {
              sfx.pickup();
              popup(seat, "Charges perdues", "info", 1200);
              for (let i = 0; i < count; i++) {
                fly(`charges-${seat}`, "discard", null, { delay: i * 0.1 });
              }
              await wait(T.fly * 0.5 + 100 * count);
              patchShown(seat, { charges: 0 });
              await wait(T.fly * 0.5);
            }
            break;
          }
          case "lives_updated": {
            const seat = e.player as number;
            const removedRaw = e.removed as CardT[];
            const addedRaw = e.added as CardT[];
            const same = (a: CardT, b: CardT) =>
              a.suit === b.suit && face(a).value === face(b).value;
            const total = (cards: CardT[]) =>
              cards.reduce((sum, c) => sum + c.value, 0);
            // D'abord ce qui part, puis ce qui vient : la recomposition se lit, et le
            // tapis suit chaque carte au moment où elle décolle ou se pose.
            if (removedRaw.length) {
              sfx.play();
              removedRaw.forEach((c, i) =>
                fly(`lives-${seat}`, "discard", face(c), { delay: i * 0.1 }),
              );
              await wait(160);
              const remaining = (seatNow(seat)?.lives ?? []).filter(
                (c) => !removedRaw.some((r) => same(r, c)),
              );
              patchShown(seat, { lives: remaining, life_total: total(remaining) });
              await wait(T.fly + 100 * (removedRaw.length - 1) - 40);
            }
            if (addedRaw.length) {
              sfx.pickup();
              addedRaw.forEach((c, i) =>
                fly("discard", `lives-${seat}`, face(c), {
                  size: sizeFor(seat),
                  delay: i * 0.1,
                }),
              );
              await wait(T.fly + 100 * (addedRaw.length - 1) - 40);
              const lives = [...(seatNow(seat)?.lives ?? []), ...addedRaw];
              patchShown(seat, { lives, life_total: total(lives) });
              sfx.play();
              popup(seat, `Vies : ${total(lives)}`, "info", 1300);
              await wait(500);
            }
            break;
          }
          case "defense_changed": {
            const target = e.target as number;
            const old = e.old as CardT | null;
            const value = (e.card as CardT).value;
            if (!shieldDone.has(target)) {
              // Sans révélation juste avant (cas théorique) : on fait l'échange ici.
              if (old) {
                fly(`shield-${target}`, "discard", face(old), { spin: -14 });
                await wait(T.fly * 0.6);
              }
              patchShown(target, { defense: e.card as CardT });
            }
            sfx.play();
            flash(target, "heal", 700);
            burst(`shield-${target}`, {
              colors: SPARK_GOLD,
              count: 14,
              speed: 160,
              size: 2.2,
              life: 0.6,
              gravity: 200,
              streak: false,
            });
            popup(target, `Bouclier ${value}`, "info", 1500);
            await wait(T.verdict);
            break;
          }
          case "died": {
            const seat = e.player as number;
            const livesRaw = seatNow(seat)?.lives ?? [];
            const lives = livesRaw.map(face);
            sfx.thud();
            vibrate([60, 40, 80]);
            shakeTable();
            flash(seat, "death", 1400, true);
            screenFx("dark");
            burst(`lives-${seat}`, {
              colors: DUST,
              count: 26,
              speed: 220,
              size: 5,
              life: 1.1,
              gravity: 250,
              streak: false,
            });
            await wait(220);
            popup(seat, "À terre", "damage", 2000, true);
            await wait(600);
            lives.forEach((c, i) =>
              fly(`lives-${seat}`, "discard", c, {
                size: sizeFor(seat),
                delay: i * 0.15,
                spin: -20,
              }),
            );
            await wait(160);
            patchShown(seat, { lives: [], life_total: 0 });
            await wait(T.fly + 150 * lives.length + 240);
            break;
          }
          case "suit_chosen": {
            const seat = e.player as number;
            const suit = e.suit as CardT["suit"];
            popup(seat, SUIT_GLYPH[suit], "info", 1600, true);
            await wait(800);
            break;
          }
          case "revival_flip": {
            const seat = e.player as number;
            const attempt = e.attempt as number;
            const card = face(e.card as CardT);
            const success = e.success as boolean;
            stage({ cards: [], tone: "reveal", caption: null, spotlight: true });
            if (attempt === 2) {
              // On coupe le paquet : les deux moitiés s'écartent, la carte du milieu sort.
              center({ split: true });
              sfx.shuffle();
              await wait(700);
            }
            sfx.pickup();
            fly("deck", "stage", null, { size: "lg", spin: 0 });
            center({ split: false });
            await wait(T.fly);
            sfx.flip();
            stage({
              cards: [card],
              caption:
                attempt === 2
                  ? `Dernière chance — ${name(seat)}`
                  : `${name(seat)} joue sa peau`,
            });
            await wait(T.flip + T.read);
            if (success) {
              sfx.bell();
              vibrate([20, 30, 20]);
              screenFx("gold");
              stage({ tone: "success", caption: "Bonne couleur !" });
              burst("stage", {
                colors: SPARK_GOLD,
                count: 40,
                speed: 300,
                size: 3,
                life: 0.9,
                gravity: 350,
              });
              shockwave("stage", { color: "rgba(229,181,74,0.9)", radius: 120 });
            } else {
              sfx.nope();
              stage({
                tone: "fail",
                caption: attempt === 2 ? "Éliminé." : "Raté…",
              });
              burst("stage", {
                colors: DUST,
                count: 18,
                speed: 120,
                size: 4,
                life: 0.9,
                gravity: 120,
                streak: false,
              });
            }
            await wait(T.verdict + 300);
            stage(null);
            fly("stage", success ? `lives-${seat}` : "discard", card, {
              size: success ? sizeFor(seat) : "ms",
              spin: success ? 6 : -18,
            });
            await wait(T.fly - 40);
            if (success) {
              const raw = e.card as CardT;
              patchShown(seat, { lives: [raw], life_total: raw.value });
            }
            await wait(140);
            break;
          }
          case "revived": {
            const seat = e.player as number;
            sfx.play();
            flash(seat, "heal", 900);
            burst(`lives-${seat}`, {
              colors: SPARK_GOLD,
              count: 22,
              speed: 200,
              size: 2.6,
              life: 0.7,
              gravity: 250,
            });
            popup(seat, "Revient !", "info", 1600, true);
            await wait(700);
            break;
          }
          case "eliminated": {
            const seat = e.player as number;
            const defense = e.defense as CardT | null;
            flash(seat, "death", 1200);
            screenFx("dark");
            popup(seat, "Éliminé", "damage", 2000, true);
            if (seat === me) sfx.lose();
            else sfx.thud();
            await wait(400);
            if (defense) {
              // Son bouclier retourne en jeu : il glisse à la défausse.
              fly(`shield-${seat}`, "discard", face(defense), { spin: -12 });
              await wait(160);
              patchShown(seat, { defense: null });
              await wait(T.fly - 160);
            }
            patchShown(seat, { alive: false });
            await wait(500);
            break;
          }
          case "deck_reshuffled": {
            sfx.shuffle();
            for (let i = 0; i < 6; i++) {
              fly("discard", "deck", null, {
                delay: i * 0.08,
                spin: i % 2 ? 24 : -24,
              });
            }
            await wait(T.fly + 80 * 6);
            break;
          }
          case "turn": {
            if (e.player === me && after.status === "playing") sfx.yourTurn();
            break;
          }
          case "game_over": {
            const mine = after.players[me]?.finish_rank;
            if (mine === 1) {
              sfx.win();
              screenFx("gold");
              burst(`seat-${me}`, {
                colors: SPARK_GOLD,
                count: 60,
                speed: 420,
                size: 3,
                life: 1.2,
                gravity: 400,
              });
            }
            await wait(1100);
            break;
          }
          default:
            break;
        }
      }
    }
  }, [onEvents, commit, patchShown, flash, popup, center, stage, shakeTable]);

  return { shown, fx };
}
