"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, animate, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Avatar from "@/components/Avatar";
import ChatPanel from "@/components/ChatPanel";
import { spawnFlight } from "@/components/FlightLayer";
import PlayingCard, { valueLabel } from "@/components/PlayingCard";
import { anchorDelta, offsetFromAnchor, registerAnchor } from "@/lib/anchors";
import { fetchPlayerByPseudo } from "@/lib/api";
import { EMOTES } from "@/lib/emotes";
import { forgetTable } from "@/lib/identity";
import { sfx, vibrate } from "@/lib/sound";
import { BOT_LABELS, NO_STATS, type CardT, type GameEvent, type GameStats } from "@/lib/types";
import { GAME } from "./meta";
import type { NineToOneSocket } from "./socket";
import type { PlayerView, RoomView } from "./types";
import { Sheet } from "@/components/Sheet";

/* La table de jeu : adversaires en haut, tas au centre, ton plateau et ta main en bas.
   Le serveur est seul juge — ici on n'affiche que sa vérité et on envoie des intentions.
   Les cartes "voyagent" entre des ancres (pioche, tas, avatars) : voir lib/anchors.ts. */

type Delta = { x: number; y: number; rotate?: number; delay?: number };

export default function GameTable({ socket, view }: { socket: NineToOneSocket; view: RoomView }) {
  const you = view.players[view.your_seat];
  const opponents = useMemo(
    () =>
      Array.from({ length: view.players.length - 1 }, (_, i) => {
        return view.players[(view.your_seat + 1 + i) % view.players.length];
      }),
    [view.players, view.your_seat]
  );
  const yourTurn = view.turn === view.your_seat;
  // Fenêtre de « bonne pioche », décidée par le serveur : carte fraîchement
  // piochée à enchaîner, ou carte cachée à retourner vite. Pas pendant son tour.
  const chaseValue = yourTurn ? null : view.chase_value;

  useEffect(() => {
    if (chaseValue !== null) {
      sfx.yourTurn();
      vibrate(20);
    }
  }, [chaseValue]);

  const [pendingValue, setPendingValue] = useState<{ value: number; copies: number } | null>(null);
  const [pendingSeven, setPendingSeven] = useState<number | null>(null); // count à poser
  const [banner, setBanner] = useState<string | null>(null);
  const [lastMove, setLastMove] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  // Dernier message de chat, affiché quelques secondes en jeu (tap = chat complet).
  const [recentMsg, setRecentMsg] = useState<{ seat: number; text: string } | null>(null);
  const chatSeenRef = useRef(0);
  useEffect(() => {
    if (socket.chat.length === 0) return;
    if (chatSeenRef.current === 0) {
      chatSeenRef.current = socket.chat.length; // historique initial : pas de bulle
      return;
    }
    if (socket.chat.length > chatSeenRef.current) {
      chatSeenRef.current = socket.chat.length;
      const last = socket.chat[socket.chat.length - 1];
      setRecentMsg(last);
      const timer = setTimeout(() => setRecentMsg(null), 4500);
      return () => clearTimeout(timer);
    }
  }, [socket.chat]);
  const [inspectSeat, setInspectSeat] = useState<number | null>(null);
  const [shaking, setShaking] = useState(false);
  const [flash, setFlash] = useState(false);
  const [nopeCard, setNopeCard] = useState<string | null>(null);
  // Carte de la main soulevée par un premier tap ("valeur-couleur") : un second tap
  // sur la même la joue. Évite de poser une carte en faisant défiler la main.
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const handKeys = (view.players[view.your_seat]?.hand ?? [])
    .map((c) => `${c.value}-${c.suit}`)
    .join(" ");
  useEffect(() => {
    // La main change ou le tour passe : plus rien de soulevé.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedKey(null);
  }, [handKeys, yourTurn]);

  // Cibles de vol pour les cartes qui entrent/sortent, fixées au moment des événements
  // serveur (juste avant le rendu de la nouvelle vue).
  const [pileExit, setPileExit] = useState<Delta | null>(null);
  const [pileFrom, setPileFrom] = useState<string | null>(null);
  const [handEntry, setHandEntry] = useState<{
    keys: string[];
    source: string | null;
    delay: number;
  }>({ keys: [], source: null, delay: 0 });
  const longPressRef = useRef(0);

  useEffect(() => {
    socket.onEvents((events: GameEvent[], nextView) => {
      // Cartes qui viennent d'entrer dans ma main (pour les faire voler à l'arrivée).
      const oldKeys = new Set(
        (view.players[view.your_seat]?.hand ?? []).map((c) => `${c.value}-${c.suit}`)
      );
      const newKeys = (nextView.players[nextView.your_seat]?.hand ?? [])
        .map((c) => `${c.value}-${c.suit}`)
        .filter((k) => !oldKeys.has(k));
      let handSource: string | null = null;

      // Pose qui déclenche aussitôt un ramassage ou une coupe : on joue la scène
      // en deux temps — la carte rejoint d'abord le tas, y repose ~1 s, puis s'en va.
      const playedEvents = events.filter((e) => e.type === "cards_played");
      const pileLeaves = events.some(
        (e) => e.type === "pile_picked_up" || e.type === "pile_cut"
      );
      const combo = playedEvents.length > 0 && pileLeaves;
      const exitDelay = combo ? 1.0 : 0;
      if (!pileLeaves) {
        // Sinon, la carte qui sort de la fenêtre d'affichage du tas (limitée aux
        // 3 dernières) rejouerait la destination du ramassage précédent : on
        // voyait une carte fantôme quitter le tas vers une main.
        setPileExit(null);
      }

      for (const event of events) {
        const seat = event.player as number;
        const pseudo = view.players[seat]?.pseudo ?? "?";
        if (event.type === "cards_played") {
          sfx.play();
          const count = event.count as number;
          const value = event.value as number;
          const cards = (event.cards as CardT[] | undefined) ?? [];
          const chase = Boolean(event.chase);
          setLastMove(
            `${seat === view.your_seat ? "Tu as" : `${pseudo} a`} ${
              chase ? "enchaîné" : "posé"
            } ${count > 1 ? `${count}×` : "le "}${valueLabel(value)}`
          );
          setPileFrom(seat === view.your_seat ? "hand" : `seat-${seat}`);
          // La carte voyage dans la couche du dessus : jamais clippée par la main
          // ni cachée sous le plateau.
          cards.forEach((card, i) =>
            spawnFlight({
              from: seat === view.your_seat ? "hand" : `seat-${seat}`,
              to: "pile",
              content: <PlayingCard card={card} size="lg" />,
              delay: i * 0.08,
              duration: 0.35,
            })
          );
          if (combo) {
            // Le tas est déjà parti côté serveur : la carte posée doit quand même
            // reposer visiblement sur le tas avant le balayage.
            cards.forEach((card, i) =>
              spawnFlight({
                from: "pile",
                to: "pile",
                content: <PlayingCard card={card} size="lg" />,
                delay: 0.33 + i * 0.08,
                duration: Math.max(exitDelay - 0.3 - i * 0.08, 0.2),
                still: true,
              })
            );
          }
          if (seat === view.your_seat) {
            handSource ??= "draw";
          } else {
            // L'adversaire repioche : uniquement s'il a réellement pioché.
            const before = view.players[seat]?.hand_count ?? 0;
            const after = nextView.players[seat]?.hand_count ?? 0;
            const drawn = Math.max(0, after - (before - count));
            for (let i = 0; i < Math.min(drawn, 3); i++) {
              spawnFlight({
                from: "draw",
                to: `seat-${seat}`,
                content: <PlayingCard faceDown size="sm" />,
                delay: 0.3 + i * 0.13,
                duration: 0.5,
              });
            }
          }
        } else if (event.type === "card_flipped") {
          sfx.flip();
          if (seat === view.your_seat) handSource = "board";
        } else if (event.type === "game_started") {
          sfx.deal();
          handSource = "draw";
        } else if (event.type === "pile_cut") {
          const delta: Delta = { x: window.innerWidth * 0.9, y: -60, rotate: 50, delay: exitDelay };
          setPileExit(delta);
          setTimeout(() => {
            sfx.cut();
            setShaking(true);
            setFlash(true);
            setTimeout(() => setShaking(false), 400);
            setTimeout(() => setFlash(false), 350);
            flashBanner("Coupé !");
          }, exitDelay * 1000);
        } else if (event.type === "pile_picked_up") {
          const mine = seat === view.your_seat;
          const targetKey = mine ? "hand" : `seat-${seat}`;
          const delta = anchorDelta("pile", targetKey);
          setPileExit(delta ? { ...delta, delay: exitDelay } : null);
          if (combo) {
            // Les cartes tout juste posées accompagnent le tas vers le ramasseur.
            for (const played of playedEvents) {
              ((played.cards as CardT[] | undefined) ?? []).forEach((card, i) =>
                spawnFlight({
                  from: "pile",
                  to: targetKey,
                  content: <PlayingCard card={card} size="lg" />,
                  delay: exitDelay + i * 0.06,
                  duration: 0.45,
                })
              );
            }
          }
          setTimeout(() => {
            sfx.pickup();
            if (mine) {
              vibrate([40, 60, 40]);
              flashBanner("Tu ne peux pas jouer : tu ramasses le tas.");
            } else {
              flashBanner(`${pseudo} ramasse le tas.`);
            }
          }, exitDelay * 1000);
          if (mine) handSource = "pile";
          setLastMove(`${mine ? "Tu as" : `${pseudo} a`} ramassé le tas`);
        } else if (event.type === "auto_played") {
          flashBanner(
            seat === view.your_seat
              ? "Temps écoulé : le serveur a joué pour toi."
              : `Temps écoulé pour ${pseudo}.`
          );
        }
      }

      if (newKeys.length) {
        setHandEntry({
          keys: newKeys,
          source: handSource ?? "draw",
          delay: handSource === "pile" ? exitDelay + 0.25 : 0,
        });
      }
    });

    function flashBanner(text: string) {
      setBanner(text);
      setTimeout(() => setBanner(null), 2200);
    }
  }, [socket, view]);

  useEffect(() => {
    // Signal discret quand ton tour arrive.
    if (yourTurn && view.status === "playing") {
      sfx.yourTurn();
      vibrate(35);
    }
  }, [yourTurn, view.status]);

  useEffect(() => {
    // Emotes ciblées : l'emoji vole de l'expéditeur vers la cible.
    const last = socket.emotes[socket.emotes.length - 1];
    if (!last || last.target === null) return;
    const key = (seat: number) => (seat === view.your_seat ? "you" : `seat-${seat}`);
    spawnFlight({
      from: key(last.seat),
      to: key(last.target),
      content: <span className="text-3xl">{EMOTES[last.emote] ?? last.emote}</span>,
      duration: 0.55,
    });
  }, [socket.emotes, view.your_seat]);

  const finished = view.status === "finished";
  useEffect(() => {
    if (!finished) return;
    const me = view.players[view.your_seat];
    const lastRank = view.players.length;
    if (me.finish_rank === 1) sfx.win();
    else if (me.finish_rank === lastRank) sfx.lose();
  }, [finished, view.players, view.your_seat]);

  function tapValue(value: number, key: string) {
    if (Date.now() - longPressRef.current < 500) return; // un appui long vient de jouer
    if (!yourTurn) return;
    if (!view.playable_values.includes(value)) {
      // Coup interdit : secousse + petit son, pour comprendre sans lire.
      sfx.nope();
      setSelectedKey(null);
      setNopeCard(key);
      setTimeout(() => setNopeCard(null), 350);
      return;
    }
    if (selectedKey !== key) {
      // Premier tap : la carte se soulève, le second la jouera.
      setSelectedKey(key);
      return;
    }
    // Second tap : la carte reste soulevée et part de là ; la sélection tombe
    // d'elle-même quand la main change (ou si le choix ci-dessous est annulé).
    const copies = eligibleCopies(you, value);
    if (copies > 1) {
      setPendingValue({ value, copies });
    } else if (value === 7) {
      setPendingSeven(1);
    } else {
      socket.play(value, 1);
    }
  }

  function longPressValue(value: number) {
    // Appui long : pose d'un coup toutes les copies de la valeur.
    if (!yourTurn || !view.playable_values.includes(value)) return;
    longPressRef.current = Date.now();
    playCount(value, eligibleCopies(you, value));
  }

  function playCount(value: number, count: number) {
    setPendingValue(null);
    if (value === 7) setPendingSeven(count);
    else socket.play(value, count);
  }

  return (
    <div className={`flex h-full min-h-0 flex-col ${shaking ? "animate-table-shake" : ""}`}>
      <OpponentsRow
        opponents={opponents}
        view={view}
        emotes={socket.emotes}
        onInspect={setInspectSeat}
      />
      <CenterTable
        view={view}
        yourTurn={yourTurn}
        pileExit={pileExit}
        pileFrom={pileFrom}
        lastMove={lastMove}
      />
      <YourArea
        you={you}
        view={view}
        yourTurn={yourTurn}
        chaseValue={chaseValue}
        handEntry={handEntry}
        nopeCard={nopeCard}
        selectedKey={selectedKey}
        onTapValue={tapValue}
        onLongPress={longPressValue}
        onFlip={(i) => socket.flip(i)}
        onChase={() => socket.chase(1)}
        onChaseFlip={(i) => socket.chaseFlip(i)}
      />
      <AnimatePresence>
        {recentMsg && !chatOpen && (
          <motion.button
            type="button"
            onClick={() => setChatOpen(true)}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute bottom-16 left-3 z-20 max-w-[75%] truncate rounded-2xl bg-black/70 px-3 py-2 text-left text-sm shadow-card backdrop-blur"
          >
            <span className="font-bold text-gold/90">
              {view.players[recentMsg.seat]?.pseudo ?? "?"}
            </span>{" "}
            {recentMsg.text}
          </motion.button>
        )}
      </AnimatePresence>

      <BottomBar you={you} view={view} socket={socket} onToggleChat={() => setChatOpen((v) => !v)} />

      {flash && <div className="pointer-events-none fixed inset-0 z-30 bg-gold/20" />}

      <AnimatePresence>
        {banner && (
          <motion.p
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="fixed inset-x-6 top-28 z-40 rounded-2xl bg-black/70 px-4 py-3 text-center font-bold shadow-card backdrop-blur"
          >
            {banner}
          </motion.p>
        )}
      </AnimatePresence>

      {pendingValue && (
        <Sheet
          onClose={() => {
            setPendingValue(null);
            setSelectedKey(null);
          }}
        >
          <p className="mb-3 text-center font-bold">
            Tu as {pendingValue.copies} {valueLabel(pendingValue.value)}. Combien en poses-tu ?
          </p>
          <div className="flex justify-center gap-2">
            {Array.from({ length: pendingValue.copies }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => playCount(pendingValue.value, n)}
                className="rounded-2xl bg-gold px-6 py-3 text-lg font-extrabold text-ink active:translate-y-0.5"
              >
                ×{n}
              </button>
            ))}
          </div>
        </Sheet>
      )}

      {pendingSeven !== null && (
        <Sheet
          onClose={() => {
            setPendingSeven(null);
            setSelectedKey(null);
          }}
        >
          <p className="mb-3 text-center font-bold">Ton 7 impose quoi au joueur suivant ?</p>
          <div className="flex justify-center gap-2">
            <button
              type="button"
              onClick={() => {
                socket.play(7, pendingSeven, "<=");
                setPendingSeven(null);
              }}
              className="rounded-2xl bg-ivory px-5 py-3 font-extrabold text-ink active:translate-y-0.5"
            >
              En dessous de 7
            </button>
            <button
              type="button"
              onClick={() => {
                socket.play(7, pendingSeven, ">=");
                setPendingSeven(null);
              }}
              className="rounded-2xl bg-gold px-5 py-3 font-extrabold text-ink active:translate-y-0.5"
            >
              Au-dessus de 7
            </button>
          </div>
        </Sheet>
      )}

      {chatOpen && (
        <Sheet onClose={() => setChatOpen(false)}>
          <ChatPanel socket={socket} view={view} />
        </Sheet>
      )}

      {inspectSeat !== null && (
        <PlayerSheet
          view={view}
          seat={inspectSeat}
          socket={socket}
          onClose={() => setInspectSeat(null)}
        />
      )}

      {finished && <Results view={view} socket={socket} />}
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Copies posables d'une valeur : la main, complétée par les cartes visibles
   quand la pose viderait toute la main (règle de complétion). */
function eligibleCopies(you: PlayerView, value: number): number {
  const hand = you.hand ?? [];
  const inHand = hand.filter((c) => c.value === value).length;
  if (inHand === hand.length) {
    return inHand + you.face_up.filter((c) => c.value === value).length;
  }
  return inHand;
}

/* Vol d'entrée : la carte part d'une ancre et rejoint sa place            */
/* ----------------------------------------------------------------------- */

function FlyIn({
  from,
  delay = 0,
  flip = false,
  children,
}: {
  from: string | null;
  delay?: number;
  flip?: boolean;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !from) return;
    const d = offsetFromAnchor(from, el);
    if (!d) return;
    // Invisible avant le départ (surtout avec un délai) : jamais de flash en place.
    el.style.opacity = "0";
    const controls = animate(
      el,
      {
        x: [d.x, 0],
        y: [d.y, 0],
        scale: [0.8, 1],
        opacity: [0, 1, 1],
        rotateY: [flip ? 120 : 0, 0],
      },
      { duration: 0.45, delay, ease: [0.25, 0.8, 0.3, 1] }
    );
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <span ref={ref} className="block will-change-transform">
      {children}
    </span>
  );
}

/* ----------------------------------------------------------------------- */
/* Plateau : cartes cachées avec les visibles posées dessus, de travers    */
/* ----------------------------------------------------------------------- */

function Board({
  faceUp,
  faceDownCount,
  size,
  mustFlip = false,
  urgent = false,
  onFlip,
}: {
  faceUp: CardT[];
  faceDownCount: number;
  size: "xxs" | "xs" | "sm" | "md";
  mustFlip?: boolean;
  urgent?: boolean;
  onFlip?: (index: number) => void;
}) {
  const slots = Math.max(faceDownCount, faceUp.length);
  if (slots === 0) return null;
  const gap = size === "xxs" ? "gap-0.5" : size === "xs" ? "gap-1" : "gap-2";
  return (
    <div className={`flex ${gap}`}>
      {Array.from({ length: slots }).map((_, i) => (
        // Empilement décroissant : la carte visible d'un emplacement passe
        // au-dessus de la carte cachée de l'emplacement suivant.
        <div key={i} className="relative" style={{ zIndex: slots - i }}>
          {i < faceDownCount ? (
            <PlayingCard
              faceDown
              size={size}
              highlighted={mustFlip}
              onClick={(mustFlip || urgent) && onFlip ? () => onFlip(i) : undefined}
              className={urgent ? "animate-urgent" : ""}
            />
          ) : (
            <InvisibleSlot size={size} />
          )}
          {i < faceUp.length && (
            <span className="pointer-events-none absolute inset-0 -translate-y-[14%] translate-x-[10%] rotate-[9deg]">
              <PlayingCard card={faceUp[i]} size={size} />
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function InvisibleSlot({ size }: { size: "xxs" | "xs" | "sm" | "md" }) {
  const w = { xxs: "w-5", xs: "w-6", sm: "w-9", md: "w-14" }[size];
  return <span className={`block ${w} aspect-[2/3]`} />;
}

/* ----------------------------------------------------------------------- */
/* Adversaires                                                             */
/* ----------------------------------------------------------------------- */

function OpponentsRow({
  opponents,
  view,
  emotes,
  onInspect,
}: {
  opponents: PlayerView[];
  view: RoomView;
  emotes: NineToOneSocket["emotes"];
  onInspect: (seat: number) => void;
}) {
  // À 3 adversaires et plus, tout se resserre pour tenir sur les petits écrans.
  const compact = opponents.length >= 3;
  return (
    <div className="flex items-start justify-evenly gap-1 px-2 py-3 pr-14">
      {opponents.map((op) => {
        const active = view.turn === op.seat;
        const emote = emotes.findLast((e) => (e.target ?? e.seat) === op.seat);
        return (
          <div key={op.seat} className="relative flex min-w-0 flex-col items-center gap-1">
            <AnimatePresence>
              {emote && (
                <motion.span
                  key={emote.id}
                  initial={{ opacity: 0, scale: 0.4, y: 6 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ delay: emote.target !== null ? 0.5 : 0 }}
                  className="absolute -top-2 z-20 rounded-full bg-black/60 px-2 py-0.5 text-xl"
                >
                  {EMOTES[emote.emote] ?? emote.emote}
                </motion.span>
              )}
            </AnimatePresence>
            <button type="button" onClick={() => onInspect(op.seat)} className="relative">
              <span
                ref={registerAnchor(`seat-${op.seat}`)}
                className={`block rounded-full transition-shadow ${
                  active && view.turn_remaining === null ? "animate-halo" : ""
                } ${op.finish_rank ? "opacity-50" : ""}`}
              >
                <Avatar id={op.avatar} size={compact ? "sm" : "md"} dimmed={!op.connected} />
              </span>
              {active && view.turn_remaining !== null && (
                <TurnRing remaining={view.turn_remaining} total={view.turn_seconds} />
              )}
              {op.finish_rank === null && op.hand_count > 0 && (
                <span className="absolute -bottom-1 -right-2 rounded-full bg-black/70 px-1.5 text-[11px] font-bold text-ivory ring-1 ring-white/20">
                  ×{op.hand_count}
                </span>
              )}
              {op.finish_rank === 1 && (
                <span className="absolute -right-1 -top-2 text-base">👑</span>
              )}
              {!op.connected && (
                <span className="absolute -left-1 -top-1 flex size-4 items-center justify-center rounded-full bg-card-red text-[9px] ring-1 ring-black/40">
                  ⚡
                </span>
              )}
            </button>
            <span
              className={`max-w-20 truncate text-xs font-bold ${op.connected ? "" : "text-ivory-dim/50"}`}
            >
              {op.pseudo}
            </span>
            {op.finish_rank !== null ? (
              <span className="text-xs font-bold text-gold">{rankLabel(op.finish_rank)}</span>
            ) : (
              <Board
                faceUp={op.face_up}
                faceDownCount={op.face_down_count}
                size={compact ? "xxs" : "xs"}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* Anneau de compte à rebours autour de l'avatar du joueur au trait. */
function TurnRing({ remaining, total }: { remaining: number; total: number }) {
  const [gone, setGone] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setGone(true));
    return () => cancelAnimationFrame(raf);
  }, []);
  const r = 45;
  const c = 2 * Math.PI * r;
  const startOffset = c * (1 - Math.max(0, remaining) / Math.max(total, 1));
  return (
    <svg viewBox="0 0 100 100" className="pointer-events-none absolute -inset-2 -rotate-90">
      <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(0,0,0,0.45)" strokeWidth="8" />
      <circle
        cx="50"
        cy="50"
        r={r}
        fill="none"
        stroke="var(--color-gold)"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={gone ? c : startOffset}
        style={{ transition: gone ? `stroke-dashoffset ${remaining}s linear` : undefined }}
      />
    </svg>
  );
}

/* ----------------------------------------------------------------------- */
/* Centre : pioche, tas, règle en cours                                    */
/* ----------------------------------------------------------------------- */

function CenterTable({
  view,
  yourTurn,
  pileExit,
  pileFrom,
  lastMove,
}: {
  view: RoomView;
  yourTurn: boolean;
  pileExit: Delta | null;
  pileFrom: string | null;
  lastMove: string | null;
}) {
  const top = view.pile.slice(-3);
  const turnPlayer = view.turn !== null ? view.players[view.turn] : null;
  // Série en cours au sommet du tas (2 ou 3 cartes identiques) : à 4 ça coupe.
  let topRun = 0;
  if (view.pile.length > 0) {
    const topValue = view.pile[view.pile.length - 1].value;
    topRun = 1;
    for (let i = view.pile.length - 2; i >= 0 && view.pile[i].value === topValue; i--) topRun++;
  }

  return (
    <div className="flex min-h-0 grow flex-col items-center justify-center gap-2.5">
      <RuleChip view={view} />
      <div className="flex items-center gap-8">
        {/* La pioche */}
        <div
          ref={registerAnchor("draw")}
          className={`relative ${view.draw_count === 0 ? "opacity-30" : ""}`}
        >
          <PlayingCard faceDown size="lg" />
          <span className="absolute -bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-2 text-xs font-bold">
            {view.draw_count}
          </span>
        </div>
        {/* Le tas central */}
        <div ref={registerAnchor("pile")} className="relative aspect-[2/3] w-[4.8rem]">
          {view.pile.length === 0 && (
            <span className="flex h-full w-full items-center justify-center rounded-xl border-2 border-dashed border-white/20 text-xs text-ivory-dim/60">
              tas vide
            </span>
          )}
          <AnimatePresence custom={pileExit}>
            {top.map((card, i) => {
              const isTop = i === top.length - 1;
              return (
                <motion.span
                  key={`${card.value}-${card.suit}-${view.pile.length - top.length + i}`}
                  animate={{ rotate: cardAngle(card) }}
                  variants={{
                    exit: (target: Delta | null) =>
                      target
                        ? {
                            x: target.x,
                            y: target.y,
                            rotate: target.rotate ?? 0,
                            opacity: 0,
                            scale: 0.5,
                            transition: {
                              duration: 0.45,
                              delay: target.delay ?? 0,
                              ease: [0.5, 0, 0.8, 0.4],
                            },
                          }
                        : { opacity: 0, transition: { duration: 0.12 } },
                  }}
                  exit="exit"
                  className="absolute inset-0"
                >
                  {isTop && pileFrom ? (
                    // Le voyage est joué par la couche de vol ; la carte du tas
                    // apparaît au moment où le vol atterrit.
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.3, duration: 0.1 }}
                      className="block"
                    >
                      <PlayingCard card={card} size="lg" />
                    </motion.span>
                  ) : (
                    <PlayingCard card={card} size="lg" />
                  )}
                </motion.span>
              );
            })}
          </AnimatePresence>
          {view.pile.length > 3 && (
            <span className="absolute -bottom-2 left-1/2 z-10 -translate-x-1/2 rounded-full bg-black/60 px-2 text-xs font-bold">
              {view.pile.length}
            </span>
          )}
          {topRun >= 2 && (
            <motion.span
              key={topRun}
              initial={{ scale: 1.6 }}
              animate={{ scale: 1 }}
              className="absolute -right-3 -top-2 z-10 rounded-full bg-gold px-1.5 py-0.5 text-xs font-extrabold text-ink shadow-card-flat"
            >
              ×{topRun}
            </motion.span>
          )}
        </div>
      </div>
      <p
        className={`text-sm font-bold ${yourTurn ? "animate-pulse text-gold" : "text-ivory-dim/80"}`}
      >
        {yourTurn ? "À toi de jouer" : turnPlayer ? `Au tour de ${turnPlayer.pseudo}` : ""}
      </p>
      <p className="h-4 text-xs text-ivory-dim/60">{lastMove}</p>
    </div>
  );
}

/* Angle "naturel" et stable d'une carte jetée sur le tas, dérivé de son identité. */
function cardAngle(card: CardT): number {
  const hash = card.value * 31 + card.suit.charCodeAt(0) * 7 + card.suit.length * 13;
  return (hash % 19) - 9;
}

function RuleChip({ view }: { view: RoomView }) {
  let text: string | null = null;
  let arrow: "up" | "down" | null = null;
  const topCard = view.pile[view.pile.length - 1];
  if (view.constraint) {
    const label = valueLabel(view.constraint.value);
    if (view.constraint.comparator === "<=") {
      text = `Jouer ${label} ou moins`;
      arrow = "down";
    } else {
      text = `Jouer ${label} ou plus`;
      arrow = "up";
    }
  } else if (topCard?.value === 2) {
    text = "Après un 2 : tout est permis";
  }
  if (!text) return <span className="h-7" />;
  return (
    <motion.span
      key={text}
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className="flex items-center gap-1.5 rounded-full bg-gold/15 px-3 py-1 text-sm font-bold text-gold ring-1 ring-gold/40"
    >
      {arrow && (
        <motion.span
          animate={{ y: arrow === "down" ? [0, 3, 0] : [0, -3, 0] }}
          transition={{ repeat: Infinity, duration: 1.1 }}
        >
          {arrow === "down" ? "▼" : "▲"}
        </motion.span>
      )}
      {text}
    </motion.span>
  );
}

/* ----------------------------------------------------------------------- */
/* Ta zone : plateau + main triée en éventail                              */
/* ----------------------------------------------------------------------- */

function YourArea({
  you,
  view,
  yourTurn,
  chaseValue,
  handEntry,
  nopeCard,
  selectedKey,
  onTapValue,
  onLongPress,
  onFlip,
  onChase,
  onChaseFlip,
}: {
  you: PlayerView;
  view: RoomView;
  yourTurn: boolean;
  chaseValue: number | null;
  handEntry: { keys: string[]; source: string | null; delay: number };
  nopeCard: string | null;
  selectedKey: string | null;
  onTapValue: (value: number, key: string) => void;
  onLongPress: (value: number) => void;
  onFlip: (index: number) => void;
  onChase: () => void;
  onChaseFlip: (index: number) => void;
}) {
  const hand = you.hand ?? [];
  const mustFlip = yourTurn && view.must_flip;
  // Bonne pioche : main (ou visibles) avec la valeur → bouton + cartes qui pulsent ;
  // plus aucune carte jouable → retourner vite une cachée.
  const blindChase =
    chaseValue !== null && hand.length === 0 && you.face_up.length === 0;
  const directChase = chaseValue !== null && !blindChase;

  return (
    <div className="flex flex-col items-center gap-1 px-3">
      <Board
        faceUp={you.face_up}
        faceDownCount={you.face_down_count}
        size="md"
        mustFlip={mustFlip}
        urgent={blindChase}
        onFlip={blindChase ? onChaseFlip : onFlip}
      />
      {mustFlip && (
        <p className="text-sm font-bold text-gold">Choisis une carte cachée à retourner.</p>
      )}
      <AnimatePresence>
        {directChase && (
          <motion.button
            type="button"
            onClick={onChase}
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: [1, 1.06, 1], opacity: 1 }}
            exit={{ scale: 0.6, opacity: 0 }}
            transition={{ scale: { repeat: Infinity, duration: 0.55 } }}
            className="rounded-full bg-gold px-4 py-1.5 text-sm font-extrabold text-ink shadow-card"
          >
            Vite ! Enchaîne le {valueLabel(chaseValue!)}
          </motion.button>
        )}
        {blindChase && (
          <motion.p
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: [1, 1.06, 1], opacity: 1 }}
            exit={{ scale: 0.6, opacity: 0 }}
            transition={{ scale: { repeat: Infinity, duration: 0.55 } }}
            className="text-sm font-extrabold text-gold"
          >
            Vite ! Retourne une carte : un {valueLabel(chaseValue!)} s&rsquo;enchaîne !
          </motion.p>
        )}
      </AnimatePresence>

      {/* Ta main : éventail sans chevauchement quand elle est courte.
          w-max + mx-auto : centrée quand elle tient, accessible aux deux bouts
          quand elle défile (justify-center rendrait la gauche inatteignable).
          Le défilement horizontal rogne aussi en hauteur : la marge haute absorbe
          la carte soulevée (30 px + halo), le -mt garde la main à sa place. Cette
          bande chevauche le bas du plateau : elle laisse passer les taps, seules
          les cartes en reçoivent. */}
      <div
        className="pointer-events-none -mt-7 w-full overflow-x-auto pb-3 pt-11"
        ref={registerAnchor("hand")}
      >
        <div className="pointer-events-auto mx-auto flex w-max items-end px-6">
          <AnimatePresence initial={false}>
            {hand.map((card, i) => {
              const key = `${card.value}-${card.suit}`;
              const playable = yourTurn && view.playable_values.includes(card.value);
              const chaseable = chaseValue !== null && card.value === chaseValue;
              // Hors de ton tour, la main reste en couleurs : rien n'est actionnable de
              // toute façon. Le grisage distingue l'injouable pendant ton tour.
              const dimmed = yourTurn && !playable;
              const n = hand.length;
              const center = (n - 1) / 2;
              const spread = n > 4 ? Math.min(3.4, 18 / n) : 2.2;
              const rotate = (i - center) * spread;
              const lift = Math.abs(i - center) * spread * 1.1;
              const overlap = i === 0 ? "" : n <= 4 ? "ml-1.5" : n <= 7 ? "-ml-4" : "-ml-8";
              const entryIndex = handEntry.keys.indexOf(key);
              const selected = selectedKey === key;
              return (
                <motion.span
                  key={key}
                  layout
                  animate={{ y: selected ? lift - 22 : lift, opacity: 1, rotate }}
                  exit={{ opacity: 0, scale: 0.85, transition: { duration: 0.15 } }}
                  transition={{ type: "spring", stiffness: 480, damping: 32 }}
                  className={`origin-bottom ${overlap} ${selected ? "relative z-10" : ""}`}
                >
                  <FlyIn
                    from={entryIndex >= 0 ? handEntry.source : null}
                    delay={handEntry.delay + Math.max(entryIndex, 0) * 0.12}
                    flip={handEntry.source !== "pile"}
                  >
                    <span
                      onPointerDown={(e) => {
                        if (!playable) return;
                        const timer = setTimeout(() => onLongPress(card.value), 450);
                        const clear = () => clearTimeout(timer);
                        e.currentTarget.addEventListener("pointerup", clear, { once: true });
                        e.currentTarget.addEventListener("pointerleave", clear, { once: true });
                      }}
                      className={`block ${nopeCard === key ? "animate-nope" : ""}`}
                    >
                      <PlayingCard
                        card={card}
                        size="lg"
                        highlighted={playable}
                        selected={selected}
                        onClick={
                          chaseable
                            ? onChase
                            : yourTurn
                              ? () => onTapValue(card.value, key)
                              : undefined
                        }
                        className={
                          chaseable ? "animate-urgent" : dimmed ? "opacity-70 saturate-[0.6]" : ""
                        }
                      />
                    </span>
                  </FlyIn>
                </motion.span>
              );
            })}
          </AnimatePresence>
          {hand.length === 0 && !mustFlip && you.finish_rank === null && (
            <span className="pb-3 text-sm text-ivory-dim/70">Main vide…</span>
          )}
          {you.finish_rank !== null && (
            <span className="pb-3 font-bold text-gold">
              Tu as fini {rankLabel(you.finish_rank)} !
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function BottomBar({
  you,
  view,
  socket,
  onToggleChat,
}: {
  you: PlayerView;
  view: RoomView;
  socket: NineToOneSocket;
  onToggleChat: () => void;
}) {
  const myEmote = socket.emotes.findLast((e) => (e.target ?? e.seat) === you.seat);
  const myTurn = view.turn === you.seat;
  return (
    <div className="relative flex items-center gap-1.5 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
      <span className="relative">
        <span ref={registerAnchor("you")} className="block">
          <Avatar id={you.avatar} size="sm" />
        </span>
        {myTurn && view.turn_remaining !== null && (
          <TurnRing remaining={view.turn_remaining} total={view.turn_seconds} />
        )}
      </span>
      <AnimatePresence>
        {myEmote && (
          <motion.span
            key={myEmote.id}
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ delay: myEmote.target !== null ? 0.5 : 0 }}
            className="absolute -top-8 left-2 z-20 rounded-full bg-black/60 px-2 py-0.5 text-xl"
          >
            {EMOTES[myEmote.emote] ?? myEmote.emote}
          </motion.span>
        )}
      </AnimatePresence>
      <span className="mr-1 max-w-28 truncate text-sm font-bold">{you.pseudo}</span>
      <span className="ml-auto flex shrink-0 gap-1">
        {Object.entries(EMOTES).map(([id, emoji]) => (
          <button
            key={id}
            type="button"
            onClick={() => socket.sendEmote(id)}
            className="rounded-full bg-black/25 px-1 py-0.5 ring-1 ring-white/10 active:scale-90"
            aria-label={`Envoyer ${emoji}`}
          >
            {emoji}
          </button>
        ))}
        <button
          type="button"
          onClick={onToggleChat}
          className="rounded-full bg-black/25 px-1.5 py-0.5 ring-1 ring-white/10 active:scale-90"
          aria-label="Ouvrir le chat"
        >
          💬
        </button>
      </span>
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Fiche joueur : stats publiques + emote ciblée                           */
/* ----------------------------------------------------------------------- */

function PlayerSheet({
  view,
  seat,
  socket,
  onClose,
}: {
  view: RoomView;
  seat: number;
  socket: NineToOneSocket;
  onClose: () => void;
}) {
  const player = view.players[seat];
  const profile = useQuery({
    queryKey: ["profile", player.pseudo],
    queryFn: () => fetchPlayerByPseudo(player.pseudo),
    enabled: !player.bot, // un bot n'a pas de profil
  });
  return (
    <Sheet onClose={onClose}>
      <div className="flex items-center gap-3">
        <Avatar id={player.avatar} size="lg" />
        <div>
          <p className="text-lg font-extrabold">{player.pseudo}</p>
          {player.bot ? (
            <p className="text-sm text-ivory-dim/80">Bot {BOT_LABELS[player.bot].toLowerCase()}</p>
          ) : profile.data ? (
            <ProfileStats stats={profile.data.stats[GAME.slug] ?? NO_STATS} />
          ) : (
            <p className="text-sm text-ivory-dim/60">
              {player.connected ? "" : "Hors ligne · "}Chargement des stats…
            </p>
          )}
        </div>
      </div>
      <p className="mb-2 mt-4 text-sm font-bold text-ivory-dim/80">Lui lancer une emote</p>
      <div className="flex gap-2">
        {Object.entries(EMOTES).map(([id, emoji]) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              socket.sendEmote(id, seat);
              onClose();
            }}
            className="rounded-full bg-black/25 px-3 py-2 text-2xl ring-1 ring-white/10 active:scale-90"
            aria-label={`Lancer ${emoji}`}
          >
            {emoji}
          </button>
        ))}
      </div>
    </Sheet>
  );
}

/* ----------------------------------------------------------------------- */
/* Fin de partie : podium, confettis, stats, revanche                      */
/* ----------------------------------------------------------------------- */

const CONFETTI_COLORS = ["#e5b54a", "#c3402f", "#2f6bc3", "#faf7ee", "#2a8f6d"];

type ConfettiPiece = {
  id: number;
  x: number;
  delay: number;
  duration: number;
  rotate: number;
  color: string;
  w: number;
};

function Confetti() {
  const [pieces, setPieces] = useState<ConfettiPiece[]>([]);
  useEffect(() => {
    // Généré hors rendu : Math.random est interdit pendant le rendu React.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPieces(
      Array.from({ length: 44 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        delay: Math.random() * 1.2,
        duration: 2.6 + Math.random() * 1.6,
        rotate: Math.random() * 720 - 360,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        w: 6 + Math.random() * 6,
      }))
    );
  }, []);
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {pieces.map((p) => (
        <motion.span
          key={p.id}
          initial={{ y: "-10vh", opacity: 1, rotate: 0 }}
          animate={{ y: "110vh", opacity: [1, 1, 0.7], rotate: p.rotate }}
          transition={{ duration: p.duration, delay: p.delay, ease: "linear" }}
          className="absolute top-0 block rounded-[2px]"
          style={{ left: `${p.x}%`, width: p.w, height: p.w * 1.6, background: p.color }}
        />
      ))}
    </div>
  );
}

function ProfileStats({ stats }: { stats: GameStats }) {
  const rate = stats.played > 0 ? Math.round((stats.won / stats.played) * 100) : 0;
  return (
    <p className="text-sm text-ivory-dim/80">
      {stats.played} parties · {stats.won} gagnées · {rate}% de victoires
    </p>
  );
}

function Results({ view, socket }: { view: RoomView; socket: NineToOneSocket }) {
  const ranked = [...view.players].sort((a, b) => (a.finish_rank ?? 99) - (b.finish_rank ?? 99));
  const loserRank = ranked.length;
  const youLost = view.players[view.your_seat].finish_rank === loserRank;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm">
      {!youLost && <Confetti />}
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="w-full max-w-sm rounded-3xl bg-felt-800 p-6 ring-1 ring-white/15"
      >
        <h2 className="mb-4 text-center text-2xl font-extrabold">
          {youLost ? "Perdu…" : "Fin de partie"}
        </h2>
        <ul className="mb-4 flex flex-col gap-2">
          {ranked.map((player, i) => (
            <motion.li
              key={player.seat}
              initial={{ x: -30, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ delay: 0.15 + i * 0.12 }}
              className={`flex items-center gap-3 rounded-2xl p-2 ${
                player.finish_rank === 1 ? "bg-gold/15 ring-1 ring-gold/50" : "bg-black/20"
              }`}
            >
              <span className="relative">
                <Avatar id={player.avatar} size="sm" />
                {player.finish_rank === 1 && (
                  <span className="absolute -right-1.5 -top-2 text-sm">👑</span>
                )}
              </span>
              <span className="font-bold">{player.pseudo}</span>
              {(view.stats.pickups[String(player.seat)] ?? 0) > 0 && (
                <span className="text-xs text-ivory-dim/60">
                  {view.stats.pickups[String(player.seat)]} ramassage
                  {view.stats.pickups[String(player.seat)] > 1 ? "s" : ""}
                </span>
              )}
              <span
                className={`ml-auto text-sm font-bold ${
                  player.finish_rank === loserRank ? "text-card-red" : "text-gold"
                }`}
              >
                {player.finish_rank === loserRank
                  ? "perd la partie"
                  : rankLabel(player.finish_rank ?? 0)}
              </span>
            </motion.li>
          ))}
        </ul>
        <p className="mb-4 text-center text-xs text-ivory-dim/60">
          {view.stats.moves} coups joués cette manche
        </p>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => socket.rematch()}
            className="rounded-2xl bg-gold py-3 text-center font-extrabold text-ink active:translate-y-0.5"
          >
            Revanche !
          </button>
          <Link
            href={GAME.path}
            onClick={() => forgetTable(GAME.slug)}
            className="rounded-2xl bg-black/25 py-3 text-center font-bold text-ivory-dim ring-1 ring-white/15"
          >
            Retour à l&rsquo;accueil
          </Link>
        </div>
      </motion.div>
    </div>
  );
}

function rankLabel(rank: number): string {
  return rank === 1 ? "1er" : `${rank}e`;
}
