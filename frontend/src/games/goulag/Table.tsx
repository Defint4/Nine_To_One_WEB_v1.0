"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import PlayingCard from "@/components/PlayingCard";
import { Sheet } from "@/components/Sheet";
import type { CardT } from "@/lib/types";
import { SUIT_GLYPH, SUIT_LABEL, face } from "./cards";
import { GAME } from "./meta";
import type { GoulagSocket } from "./socket";
import type { ActionKind, PlayerView, RoomView, SuitName } from "./types";

/* La table du Goulag, vue de ta place. Les adversaires sont assis autour d'un ovale
   dans l'ordre réel des tours (ton voisin de gauche joue après toi) ; chacun a son
   tapis : deux vies posées à plat, le bouclier couché devant, les charges face cachée.
   Le tapis est en vraie perspective ; les objets vivent dans leur propre petit
   espace 3D (inclinaison, relief), ce qui garde les cartes nettes et tapables. */

export default function Table({ socket, view }: { socket: GoulagSocket; view: RoomView }) {
  const me = view.your_seat;
  const you = view.players[me];
  const n = view.players.length;
  const opponents = Array.from({ length: n - 1 }, (_, i) => view.players[(me + 1 + i) % n]);
  const yourTurn = view.turn === me && view.status === "playing";
  const targeting = yourTurn && view.phase === "target";
  const canTarget = (p: PlayerView) =>
    targeting && p.alive && (view.pending_action === "defend" || p.seat !== me);
  const active = view.status === "playing" ? (view.reviving ?? view.turn) : null;

  return (
    <div className="relative flex h-full flex-col">
      <Banner view={view} you={you} />

      {/* Le tapis et les adversaires */}
      <div className="relative min-h-0 flex-1">
        <Felt />
        {opponents.map((p, i) => (
          <OpponentSeat
            key={p.seat}
            player={p}
            place={seatPlacement(i + 1, n)}
            active={active === p.seat}
            targetable={canTarget(p)}
            onTarget={() => socket.target(p.seat)}
          />
        ))}
        <Piles view={view} />
      </div>

      {/* Ta place */}
      <YourZone
        socket={socket}
        view={view}
        you={you}
        yourTurn={yourTurn}
        targetable={canTarget(you)}
        active={active === me}
      />

      {view.must_choose_suit && <SuitPicker onPick={(suit) => socket.chooseSuit(suit)} />}
      {view.status === "finished" && <Results view={view} socket={socket} />}
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Disposition                                                               */
/* ----------------------------------------------------------------------- */

/* Positions (en % de la zone) des adversaires, du voisin de gauche au voisin de
   droite en passant par le fond : c'est l'ordre réel des tours (sens horaire).
   Des rangées explicites plutôt qu'une ellipse calculée : sur un téléphone, chaque
   tapis doit rester entier et ne jamais en chevaucher un autre. */
const PLACES: Record<number, [number, number][]> = {
  1: [[50, 16]],
  2: [
    [26, 22],
    [74, 22],
  ],
  3: [
    [22, 44],
    [50, 12],
    [78, 44],
  ],
  4: [
    [22, 56],
    [26, 16],
    [74, 16],
    [78, 56],
  ],
  5: [
    [22, 62],
    [24, 32],
    [50, 10],
    [76, 32],
    [78, 62],
  ],
};

function seatPlacement(k: number, n: number): { left: string; top: string } {
  const [x, y] = PLACES[n - 1][k - 1];
  return { left: `${x}%`, top: `${y}%` };
}

/* ----------------------------------------------------------------------- */
/* Le tapis en perspective                                                   */
/* ----------------------------------------------------------------------- */

function Felt() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-x-[-14%] top-[2%] h-[118%] [perspective:900px] [perspective-origin:50%_30%]"
      >
        {/* Le bord de bois, légèrement plus grand et plus bas : l'épaisseur de la table. */}
        <div
          className="absolute inset-0 rounded-[50%]"
          style={{
            transform: "rotateX(42deg) translateY(10px)",
            background: "linear-gradient(180deg, #3b2a1c, #1f150c)",
            boxShadow: "0 30px 60px rgba(0,0,0,0.55)",
          }}
        />
        {/* Le feutre. */}
        <div
          className="absolute inset-[3%] rounded-[50%]"
          style={{
            transform: "rotateX(42deg)",
            background:
              "radial-gradient(60% 55% at 50% 42%, #2b7a62 0%, #1b5443 55%, #123b2f 100%)",
            boxShadow:
              "inset 0 0 0 6px rgba(0,0,0,0.25), inset 0 0 80px rgba(0,0,0,0.35), inset 0 -20px 40px rgba(0,0,0,0.25)",
          }}
        />
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Un adversaire                                                              */
/* ----------------------------------------------------------------------- */

function OpponentSeat({
  player,
  place,
  active,
  targetable,
  onTarget,
}: {
  player: PlayerView;
  place: { left: string; top: string };
  active: boolean;
  targetable: boolean;
  onTarget: () => void;
}) {
  const dead = !player.alive;
  return (
    <div
      className="absolute -translate-x-1/2 -translate-y-1/2"
      style={{ left: place.left, top: place.top }}
    >
      <button
        type="button"
        disabled={!targetable}
        onClick={onTarget}
        aria-label={targetable ? `Viser ${player.pseudo}` : player.pseudo}
        className={`flex flex-col items-center gap-1 rounded-2xl p-1 transition ${
          targetable ? "bg-gold/15 ring-2 ring-gold shadow-[0_0_24px_rgba(229,181,74,0.5)] active:scale-95" : ""
        } ${dead ? "opacity-45 grayscale" : ""}`}
      >
        <SeatHeader player={player} active={active} size="md" />
        <Mat player={player} size="sm" />
      </button>
    </div>
  );
}

function SeatHeader({
  player,
  active,
  size,
}: {
  player: PlayerView;
  active: boolean;
  size: "md" | "lg";
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="relative">
        {active && (
          <motion.span
            aria-hidden
            className="absolute -inset-1 rounded-full ring-2 ring-gold"
            animate={{ opacity: [0.5, 1, 0.5], scale: [1, 1.06, 1] }}
            transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
          />
        )}
        <Avatar id={player.avatar} size={size} dimmed={!player.connected} />
      </span>
      <span className="flex flex-col leading-tight">
        <span className="max-w-[5.25rem] truncate text-xs font-bold">{player.pseudo}</span>
        {player.hawk_eye && player.alive && (
          <span className="text-[10px] font-semibold text-gold">Œil de faucon</span>
        )}
      </span>
    </div>
  );
}

/* Le tapis d'un joueur : bouclier couché, deux vies, charges. Chaque carte a sa
   propre inclinaison, comme posée sur la table et vue de ta place. */
function Mat({ player, size }: { player: PlayerView; size: "sm" | "md" }) {
  const dead = !player.alive;
  const lifeCards = player.lives;
  return (
    <div className="flex items-end gap-1.5">
      {player.defense && (
        <Shield card={player.defense} size={size} dimmed={dead} />
      )}
      <div className="relative flex flex-col items-center">
        <div className="flex [perspective:500px]">
          {lifeCards.map((card, i) => (
            <Laid key={`${card.value}-${card.suit}`} index={i} size={size}>
              <PlayingCard card={face(card)} size={size} />
            </Laid>
          ))}
          {lifeCards.length === 0 && (
            <span
              className={`${size === "sm" ? "h-[3.375rem] w-9" : "h-[5.25rem] w-14"} rounded border border-dashed border-ivory-dim/40`}
            />
          )}
        </div>
        <LifeBadge total={player.life_total} alive={player.alive} size={size} />
      </div>
      {player.charges > 0 && (
        <div className="relative [perspective:500px]" aria-label={`${player.charges} charge(s)`}>
          {Array.from({ length: player.charges }, (_, i) => (
            <span
              key={i}
              className={i === 0 ? "block" : "absolute left-0 top-0"}
              style={{ transform: `translate(${i * 3}px, ${-i * 3}px) rotateX(14deg)` }}
            >
              <PlayingCard faceDown size={size === "sm" ? "xs" : "sm"} />
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* Une carte posée à plat, vue d'en face : légèrement inclinée, avec son ombre. */
function Laid({
  index,
  size,
  children,
}: {
  index: number;
  size: "sm" | "md";
  children: React.ReactNode;
}) {
  const overlap = index === 0 ? "" : size === "sm" ? "-ml-3" : "-ml-4";
  return (
    <span
      className={`block ${overlap} drop-shadow-[0_6px_6px_rgba(0,0,0,0.35)]`}
      style={{ transform: `rotateX(14deg) rotateZ(${index === 0 ? -4 : 4}deg)` }}
    >
      {children}
    </span>
  );
}

/* Le bouclier : la carte de défense couchée devant les vies, sa valeur en médaillon. */
function Shield({ card, size, dimmed }: { card: CardT; size: "sm" | "md"; dimmed: boolean }) {
  const w = size === "sm" ? "w-[3.375rem]" : "w-[5.25rem]";
  const h = size === "sm" ? "h-9" : "h-14";
  return (
    <div className={`relative ${w} ${h} shrink-0 [perspective:500px]`}>
      <span
        className="absolute left-1/2 top-1/2 block drop-shadow-[0_5px_5px_rgba(0,0,0,0.4)]"
        style={{ transform: "translate(-50%, -50%) rotateX(14deg) rotateZ(-90deg)" }}
      >
        <PlayingCard card={face(card)} size={size} />
      </span>
      <span
        className={`absolute -bottom-1.5 left-1/2 -translate-x-1/2 rounded-full bg-ink px-1.5 text-[10px] font-extrabold leading-4 text-ivory ring-1 ring-white/25 ${
          dimmed ? "opacity-60" : ""
        }`}
      >
        {card.value}
      </span>
    </div>
  );
}

function LifeBadge({ total, alive, size }: { total: number; alive: boolean; size: "sm" | "md" }) {
  const low = alive && total <= 3;
  return (
    <span
      className={`-mt-1.5 rounded-full px-2 font-extrabold leading-5 ring-1 ring-white/20 ${
        size === "sm" ? "text-xs" : "text-sm"
      } ${!alive ? "bg-black/60 text-ivory-dim/70" : low ? "bg-card-red text-ivory" : "bg-ink text-gold"}`}
    >
      {alive ? total : "†"}
    </span>
  );
}

/* ----------------------------------------------------------------------- */
/* Le centre : pioche et défausse                                             */
/* ----------------------------------------------------------------------- */

function Piles({ view }: { view: RoomView }) {
  return (
    <div className="pointer-events-none absolute left-1/2 top-[84%] flex -translate-x-1/2 -translate-y-1/2 items-end gap-5 [perspective:600px]">
      <div className="relative flex flex-col items-center">
        <div className="relative h-[3.375rem] w-9">
          {[2, 1, 0].map((i) => (
            <span
              key={i}
              className="absolute left-0 top-0 block"
              style={{ transform: `translateY(${-i * 2}px) rotateX(14deg)` }}
            >
              <PlayingCard faceDown size="sm" />
            </span>
          ))}
        </div>
        <span className="mt-1 text-[10px] font-semibold text-ivory-dim/70">{view.draw_count}</span>
      </div>
      <div className="relative flex flex-col items-center">
        <div className="relative h-[3.375rem] w-9">
          {view.discard_top ? (
            <span
              className="absolute left-0 top-0 block drop-shadow-[0_4px_4px_rgba(0,0,0,0.35)]"
              style={{ transform: "rotateX(14deg) rotateZ(6deg)" }}
            >
              <PlayingCard card={face(view.discard_top)} size="sm" />
            </span>
          ) : (
            <span className="block h-full w-full rounded border border-dashed border-ivory-dim/30" />
          )}
        </div>
        <span className="mt-1 text-[10px] font-semibold text-ivory-dim/70">{view.discard_count}</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Le bandeau du haut : qui joue, quelle phase                                */
/* ----------------------------------------------------------------------- */

function Banner({ view, you }: { view: RoomView; you: PlayerView }) {
  let text: string;
  if (view.status !== "playing") text = "";
  else if (view.phase === "revival") {
    const dead = view.players[view.reviving ?? 0];
    text = dead.seat === you.seat ? "Tu es à terre. Choisis ta couleur." : `${dead.pseudo} joue sa peau…`;
  } else if (view.turn === you.seat) {
    text = view.phase === "target" ? "Désigne ta cible." : "À toi de jouer.";
  } else {
    const p = view.players[view.turn ?? 0];
    text = view.phase === "target" ? `${p.pseudo} choisit sa cible…` : `Au tour de ${p.pseudo}.`;
  }
  return (
    <div className="pointer-events-none relative z-10 flex h-11 items-center justify-center pr-14 pl-4">
      <AnimatePresence mode="wait">
        <motion.p
          key={text}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 6 }}
          transition={{ duration: 0.18 }}
          className="truncate text-sm font-bold text-ivory-dim"
        >
          {text}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Ta place : ton tapis et tes actions                                        */
/* ----------------------------------------------------------------------- */

function YourZone({
  socket,
  view,
  you,
  yourTurn,
  targetable,
  active,
}: {
  socket: GoulagSocket;
  view: RoomView;
  you: PlayerView;
  yourTurn: boolean;
  targetable: boolean;
  active: boolean;
}) {
  const announcing = yourTurn && view.phase === "action";
  return (
    <div className="relative z-10 flex flex-col gap-2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2">
      <div className="flex items-end justify-between gap-3">
        <button
          type="button"
          disabled={!targetable}
          onClick={() => socket.target(you.seat)}
          aria-label={targetable ? "Garder cette défense pour toi" : "Ton tapis"}
          className={`rounded-2xl p-1.5 ${
            targetable ? "bg-gold/15 ring-2 ring-gold shadow-[0_0_24px_rgba(229,181,74,0.5)] active:scale-95" : ""
          } ${you.alive ? "" : "opacity-45 grayscale"}`}
        >
          <Mat player={you} size="md" />
        </button>
        <SeatHeader player={you} active={active} size="lg" />
      </div>

      <div className="min-h-[4.75rem]">
        <AnimatePresence mode="wait">
          {announcing ? (
            <motion.div
              key="actions"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="flex items-stretch gap-2"
            >
              {view.peek && (
                <div className="flex flex-col items-center justify-center rounded-2xl bg-black/30 px-2 ring-1 ring-gold/40">
                  <span className="mb-1 text-[10px] font-bold text-gold">Tu vois</span>
                  <span style={{ transform: "rotateX(10deg)" }} className="[perspective:300px]">
                    <PlayingCard card={face(view.peek)} size="sm" />
                  </span>
                </div>
              )}
              <ActionButton kind="defend" onClick={() => socket.announce("defend")}>
                Défense
              </ActionButton>
              <ActionButton
                kind="charge"
                disabled={!view.can_charge}
                onClick={() => socket.announce("charge")}
              >
                Charge
              </ActionButton>
              <ActionButton kind="attack" onClick={() => socket.announce("attack")}>
                Attaque
              </ActionButton>
            </motion.div>
          ) : yourTurn && view.phase === "target" && view.drawn ? (
            <motion.div
              key="target"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="flex items-center gap-3 rounded-2xl bg-black/30 p-2 ring-1 ring-white/10"
            >
              <span className="[perspective:300px]" style={{ transform: "rotateX(10deg)" }}>
                <PlayingCard card={face(view.drawn)} size="md" />
              </span>
              <p className="text-sm font-semibold text-ivory-dim">
                {view.pending_action === "attack"
                  ? `Tu attaques avec ${view.drawn.value}${you.charges ? ` et ${you.charges} charge${you.charges > 1 ? "s" : ""}` : ""}. Touche un adversaire.`
                  : `Un ${view.drawn.value} en défense : pour toi, ou pour quelqu'un d'autre ?`}
              </p>
            </motion.div>
          ) : (
            <motion.p
              key="wait"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="pt-6 text-center text-sm text-ivory-dim/60"
            >
              {you.alive ? "" : "Tu es éliminé. La partie continue sans toi."}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function ActionButton({
  kind,
  disabled,
  onClick,
  children,
}: {
  kind: ActionKind;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const tone = {
    defend: "bg-felt-600 text-ivory ring-1 ring-white/15",
    charge: "bg-ink text-ivory ring-1 ring-white/15",
    attack: "bg-gold text-ink",
  }[kind];
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex-1 rounded-2xl py-4 text-base font-extrabold shadow-card enabled:active:translate-y-0.5 disabled:opacity-40 ${tone}`}
    >
      {children}
    </button>
  );
}

/* ----------------------------------------------------------------------- */
/* Résurrection : choisir sa couleur                                          */
/* ----------------------------------------------------------------------- */

function SuitPicker({ onPick }: { onPick: (suit: SuitName) => void }) {
  const suits: SuitName[] = ["hearts", "diamonds", "clubs", "spades"];
  return (
    <Sheet onClose={() => {}}>
      <h2 className="mb-1 text-center text-lg font-extrabold">Tu es à terre.</h2>
      <p className="mb-4 text-center text-sm text-ivory-dim/80">
        Choisis une couleur : si la prochaine carte est de cette couleur, tu revis avec.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {suits.map((suit) => (
          <button
            key={suit}
            type="button"
            onClick={() => onPick(suit)}
            className={`flex items-center justify-center gap-2 rounded-2xl bg-white py-4 text-xl font-extrabold ring-1 ring-white/20 active:translate-y-0.5 ${
              suit === "hearts" || suit === "diamonds" ? "text-card-red" : "text-ink"
            }`}
          >
            <span className="text-2xl">{SUIT_GLYPH[suit]}</span> {SUIT_LABEL[suit]}
          </button>
        ))}
      </div>
    </Sheet>
  );
}

/* ----------------------------------------------------------------------- */
/* Fin de partie                                                               */
/* ----------------------------------------------------------------------- */

function Results({ view, socket }: { view: RoomView; socket: GoulagSocket }) {
  const ranked = [...view.players].sort((a, b) => (a.finish_rank ?? 99) - (b.finish_rank ?? 99));
  const winner = ranked[0];
  const won = winner.seat === view.your_seat;
  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-felt-900/80 px-6 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex w-full max-w-sm flex-col gap-3 rounded-3xl bg-felt-800 p-5 ring-1 ring-white/10"
      >
        <h2 className="text-center text-2xl font-extrabold">
          {won ? "Dernier debout." : `${winner.pseudo} survit.`}
        </h2>
        <ol className="flex flex-col gap-1">
          {ranked.map((p) => (
            <li key={p.seat} className="flex items-center gap-2 rounded-xl bg-black/25 p-2">
              <span className="w-5 text-center text-sm font-extrabold text-gold">{p.finish_rank}</span>
              <Avatar id={p.avatar} size="sm" />
              <span className="font-bold">{p.pseudo}</span>
            </li>
          ))}
        </ol>
        <button
          type="button"
          onClick={() => socket.rematch()}
          className="rounded-2xl bg-gold py-3 text-center font-extrabold text-ink active:translate-y-0.5"
        >
          Revanche !
        </button>
        <Link
          href={GAME.path}
          className="rounded-2xl bg-black/25 py-3 text-center font-bold text-ivory-dim ring-1 ring-white/15"
        >
          Retour à l&rsquo;accueil
        </Link>
      </motion.div>
    </div>
  );
}
