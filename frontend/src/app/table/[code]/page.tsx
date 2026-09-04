"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Avatar from "@/components/Avatar";
import ChatPanel, { RecentChat } from "@/components/ChatPanel";
import FlightLayer from "@/components/FlightLayer";
import GameTable from "@/components/GameTable";
import PlayingCard from "@/components/PlayingCard";
import { Sheet } from "@/components/Sheet";
import { joinRoom } from "@/lib/api";
import { EMOTES } from "@/lib/emotes";
import { currentProfile, forgetTable, rememberTable, type StoredProfile } from "@/lib/identity";
import {
  applyFelt,
  BACK_STYLES,
  FELT_STYLES,
  setPref,
  usePrefs,
  type BackStyle,
  type FeltStyle,
} from "@/lib/prefs";
import { preloadCards } from "@/lib/preloadCards";
import { isMuted, preloadSounds, setMuted } from "@/lib/sound";
import { BOT_LABELS, type BotDifficulty, type PlayerView, type RoomView } from "@/lib/types";
import { useRoomSocket, type RoomSocket } from "@/lib/useRoomSocket";

export default function TablePage() {
  const { code } = useParams<{ code: string }>();
  const router = useRouter();
  const [profile, setProfile] = useState<StoredProfile | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joined, setJoined] = useState(false);

  useEffect(() => {
    const current = currentProfile();
    if (!current) {
      router.replace("/");
      return;
    }
    // Lecture localStorage impossible côté serveur : l'identité arrive après montage.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProfile(current);
    joinRoom(current.token, code)
      .then(() => {
        rememberTable(code);
        setJoined(true);
      })
      .catch((e) => {
        forgetTable();
        setJoinError(e instanceof Error ? e.message : "Impossible de rejoindre.");
      });
  }, [code, router]);

  useEffect(() => {
    // Précharge les 52 faces et les sons pour éviter tout accroc en pleine partie.
    preloadCards();
    preloadSounds();
    applyFelt();
  }, []);

  useEffect(() => {
    // L'écran ne doit pas s'éteindre en pleine partie.
    let lock: { release: () => Promise<void> } | null = null;
    async function acquire() {
      try {
        lock = await navigator.wakeLock?.request("screen");
      } catch {
        /* non supporté ou refusé : sans gravité */
      }
    }
    void acquire();
    const onVisible = () => {
      if (document.visibilityState === "visible") void acquire();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      void lock?.release().catch(() => {});
    };
  }, []);

  if (joinError) return <Blocked message={joinError} />;
  if (!profile || !joined) return <Connecting />;
  return <Room code={code} token={profile.token} />;
}

/* Battage de cartes en guise d'écran de connexion. */
function Connecting() {
  return (
    <Centered>
      <div className="relative mb-4 h-16 w-16">
        <motion.span
          className="absolute left-1 top-0"
          animate={{ rotate: [-14, 10, -14], y: [0, -6, 0] }}
          transition={{ repeat: Infinity, duration: 1.1, ease: "easeInOut" }}
        >
          <PlayingCard faceDown size="sm" />
        </motion.span>
        <motion.span
          className="absolute left-6 top-1"
          animate={{ rotate: [12, -8, 12], y: [0, -10, 0] }}
          transition={{ repeat: Infinity, duration: 1.1, ease: "easeInOut", delay: 0.15 }}
        >
          <PlayingCard faceDown size="sm" />
        </motion.span>
      </div>
      Connexion à la table…
    </Centered>
  );
}

function Room({ code, token }: { code: string; token: string }) {
  const socket = useRoomSocket(code, token);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const router = useRouter();

  const rematchCode = socket.rematchCode;
  useEffect(() => {
    // Quelqu'un a lancé la revanche : toute la table bascule sur la nouvelle partie.
    if (rematchCode) {
      rememberTable(rematchCode);
      router.push(`/table/${rematchCode}`);
    }
  }, [rematchCode, router]);

  if (socket.closedReason) return <Blocked message={socket.closedReason} />;
  if (!socket.view) return <Connecting />;
  const inLobby = socket.view.status === "lobby";

  return (
    <main className="relative mx-auto flex h-[calc(100svh-env(safe-area-inset-top,0px))] w-full max-w-md flex-col overflow-hidden">
      <button
        type="button"
        onClick={() => setSettingsOpen(true)}
        aria-label="Paramètres"
        className="absolute right-3 top-3 z-30 rounded-full bg-black/30 p-2.5 text-ivory-dim ring-1 ring-white/15 backdrop-blur-sm active:scale-90"
      >
        <GearIcon />
      </button>

      {inLobby ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-5">
          <Lobby socket={socket} view={socket.view} />
        </div>
      ) : (
        <div className="min-h-0 flex-1">
          <GameTable socket={socket} view={socket.view} />
        </div>
      )}

      <FlightLayer />

      {settingsOpen && (
        <SettingsSheet
          view={socket.view}
          socket={socket}
          inLobby={inLobby}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {socket.error && (
        <p className="fixed inset-x-4 top-[calc(1rem+env(safe-area-inset-top,0px))] z-50 rounded-xl bg-card-red px-4 py-3 text-center font-bold text-ivory shadow-card">
          {socket.error}
        </p>
      )}
    </main>
  );
}

/* ----------------------------------------------------------------------- */
/* Paramètres : sons, quitter                                              */
/* ----------------------------------------------------------------------- */

function SettingsSheet({
  view,
  socket,
  inLobby,
  onClose,
}: {
  view: RoomView;
  socket: RoomSocket;
  inLobby: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const prefs = usePrefs();
  const [muted, setMutedState] = useState(false);
  const [showRules, setShowRules] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMutedState(isMuted());
  }, []);

  if (showRules) return <RulesSheet onClose={() => setShowRules(false)} />;

  return (
    <Sheet onClose={onClose}>
      <h2 className="mb-4 text-center text-lg font-extrabold">
        Table <span className="tracking-widest text-gold">{view.code}</span>
      </h2>
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => {
            setMuted(!muted);
            setMutedState(!muted);
          }}
          className="flex items-center justify-between rounded-2xl bg-black/25 p-4 ring-1 ring-white/10"
        >
          <span className="font-bold">Sons</span>
          <span
            className={`rounded-full px-3 py-1 text-sm font-bold ${
              muted ? "bg-white/10 text-ivory-dim/70" : "bg-gold text-ink"
            }`}
          >
            {muted ? "Coupés" : "Activés"}
          </span>
        </button>

        <div className="rounded-2xl bg-black/25 p-4 ring-1 ring-white/10">
          <p className="mb-2 font-bold">Dos des cartes</p>
          <div className="flex gap-3">
            {(Object.keys(BACK_STYLES) as BackStyle[]).map((style) => (
              <button
                key={style}
                type="button"
                aria-label={BACK_STYLES[style]}
                onClick={() => setPref("back", style)}
                className={`rounded-lg p-1 ${prefs.back === style ? "ring-2 ring-gold" : ""}`}
              >
                <BackPreview style={style} />
              </button>
            ))}
          </div>
          <p className="mb-2 mt-4 font-bold">Tapis</p>
          <div className="flex gap-3">
            {(Object.keys(FELT_STYLES) as FeltStyle[]).map((style) => (
              <button
                key={style}
                type="button"
                aria-label={FELT_STYLES[style]}
                onClick={() => setPref("felt", style)}
                className={`size-10 rounded-full ring-2 ${
                  prefs.felt === style ? "ring-gold" : "ring-white/20"
                }`}
                style={{
                  background: { green: "#1b5443", navy: "#1a3354", wine: "#541a25" }[style],
                }}
              />
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowRules(true)}
          className="rounded-2xl bg-black/25 p-4 text-left font-bold ring-1 ring-white/10"
        >
          Règles du jeu
        </button>

        <button
          type="button"
          onClick={() => {
            socket.leave();
            if (inLobby) forgetTable();
            router.push("/");
          }}
          className="rounded-2xl bg-card-red/90 p-4 font-extrabold text-ivory ring-1 ring-white/10 active:translate-y-0.5"
        >
          Quitter la {inLobby ? "table" : "partie"}
        </button>
        {!inLobby && (
          <p className="text-center text-sm text-ivory-dim/70">
            Ta place reste réservée : tu pourras revenir depuis l&rsquo;accueil.
          </p>
        )}
      </div>
    </Sheet>
  );
}

function BackPreview({ style }: { style: BackStyle }) {
  const css: Record<BackStyle, React.CSSProperties> = {
    classic: {
      background:
        "repeating-linear-gradient(45deg, rgba(255,255,255,0.08) 0 3px, transparent 3px 9px), #1b5443",
    },
    crimson: {
      background:
        "repeating-linear-gradient(45deg, rgba(255,255,255,0.09) 0 2px, transparent 2px 8px), repeating-linear-gradient(-45deg, rgba(255,255,255,0.09) 0 2px, transparent 2px 8px), #6e1f26",
    },
    royal: {
      background:
        "radial-gradient(rgba(255,255,255,0.18) 1px, transparent 1.5px) 0 0 / 8px 8px, #1c2f55",
    },
  };
  return <span className="block h-16 w-11 rounded-md border border-white/25" style={css[style]} />;
}

/* Rappel des règles, surtout les pouvoirs des cartes spéciales. */
function RulesSheet({ onClose }: { onClose: () => void }) {
  const powers: { card: { value: number; suit: "spades" | "hearts" | "diamonds" | "clubs" }; text: string }[] = [
    { card: { value: 2, suit: "spades" }, text: "Se pose sur tout. Le joueur suivant est libre." },
    {
      card: { value: 7, suit: "diamonds" },
      text: "Tu choisis : le suivant joue au-dessus ou en dessous de 7.",
    },
    { card: { value: 9, suit: "clubs" }, text: "Le suivant doit jouer 9 ou moins." },
    {
      card: { value: 10, suit: "hearts" },
      text: "Coupe le tas : tout part à la défausse et tu rejoues. Interdit quand il faut jouer en dessous.",
    },
  ];
  return (
    <Sheet onClose={onClose}>
      <h2 className="mb-3 text-center text-lg font-extrabold">Les règles en bref</h2>
      <p className="mb-3 text-sm text-ivory-dim/85">
        Chacun pose une carte égale ou plus forte que la précédente, et repioche à 3 cartes tant
        que la pioche dure. Bloqué ? Tu ramasses tout le tas. 4 cartes identiques d&rsquo;affilée
        coupent le tas. Main vidée : tu joues tes cartes visibles, puis tes cachées à
        l&rsquo;aveugle. Le dernier avec des cartes perd.
      </p>
      <ul className="flex flex-col gap-2">
        {powers.map(({ card, text }) => (
          <li key={card.value} className="flex items-center gap-3 rounded-2xl bg-black/25 p-2">
            <PlayingCard card={card} size="sm" />
            <span className="text-sm">{text}</span>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 fill-none stroke-current stroke-2">
      <circle cx="12" cy="12" r="3" />
      <path
        strokeLinecap="round"
        d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09c0 .68.4 1.29 1.03 1.56a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9c.27.63.88 1.03 1.56 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03Z"
      />
    </svg>
  );
}

/* ----------------------------------------------------------------------- */
/* Lobby : sièges, échange initial, prêt, chat                             */
/* ----------------------------------------------------------------------- */

function Lobby({ socket, view }: { socket: RoomSocket; view: RoomView }) {
  const you = view.players[view.your_seat];
  const [selectedHand, setSelectedHand] = useState<number | null>(null);
  const [botSheetOpen, setBotSheetOpen] = useState(false);
  const canSwap = !you.ready;
  const isCreator = view.your_seat === 0;

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
        {view.players.length < 5 && (
          <li className="flex items-center rounded-2xl border border-dashed border-ivory-dim/30 py-1.5 pl-3 pr-1.5 text-sm text-ivory-dim/60">
            <span className="grow text-center">
              {5 - view.players.length} place{view.players.length < 4 ? "s" : ""} libre
              {view.players.length < 4 ? "s" : ""}
            </span>
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
          </li>
        )}
      </ul>

      {botSheetOpen && (
        <BotSheet
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
            disabled={view.your_seat !== 0}
            onClick={() => socket.setTurnSeconds(seconds)}
            className={`rounded-full px-3 py-1 text-sm font-bold ${
              view.turn_seconds === seconds
                ? "bg-gold text-ink"
                : "bg-white/10 text-ivory-dim/70"
            } ${view.your_seat !== 0 ? "cursor-default" : "active:scale-95"}`}
          >
            {seconds === 0 ? "Sans" : `${seconds} s`}
          </button>
        ))}
      </section>

      <section className="flex flex-col gap-2">
        <p className="text-sm text-ivory-dim/80">
          {canSwap
            ? "Avant de te déclarer prêt, échange librement ta main avec tes cartes visibles."
            : "Tes cartes sont verrouillées, on attend les autres."}
        </p>
        <div className="rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
          <p className="mb-1 text-xs text-ivory-dim/70">Cartes visibles sur la table</p>
          <div className="flex gap-2">
            {you.face_up.map((card, i) => (
              <PlayingCard
                key={`${card.value}-${card.suit}`}
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
            ))}
          </div>
          <p className="mb-1 mt-3 text-xs text-ivory-dim/70">Ta main</p>
          <div className="flex gap-2">
            {(you.hand ?? []).map((card, i) => (
              <PlayingCard
                key={`${card.value}-${card.suit}`}
                card={card}
                size="md"
                disabled={!canSwap}
                selected={selectedHand === i}
                onClick={canSwap ? () => setSelectedHand(selectedHand === i ? null : i) : undefined}
              />
            ))}
          </div>
        </div>
      </section>

      <button
        type="button"
        onClick={() => socket.setReady(!you.ready)}
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
  player: PlayerView;
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
  onPick,
  onClose,
}: {
  onPick: (difficulty: BotDifficulty) => void;
  onClose: () => void;
}) {
  const choices: { id: BotDifficulty; hint: string }[] = [
    { id: "easy", hint: "Joue au hasard, une carte à la fois. Pour apprendre." },
    { id: "normal", hint: "Économe : garde ses 2 et ses 10, pose ses multiples." },
    { id: "hard", hint: "Réseau entraîné par auto-jeu : compte les cartes, enchaîne." },
  ];
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

function RobotIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} fill-none stroke-current stroke-2`} aria-hidden>
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path strokeLinecap="round" d="M12 8V4M9 4h6M2 13v3M22 13v3M9 17h6" />
      <circle cx="9" cy="13" r="1.2" className="fill-current" />
      <circle cx="15" cy="13" r="1.2" className="fill-current" />
    </svg>
  );
}

/* ----------------------------------------------------------------------- */
/* Chat + emotes (lobby)                                                   */
/* ----------------------------------------------------------------------- */

function LobbyChat({ socket, view }: { socket: RoomSocket; view: RoomView }) {
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
              <span className="font-bold text-gold/90">
                {view.players[e.seat]?.pseudo ?? "?"}
              </span>{" "}
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

/* ----------------------------------------------------------------------- */

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center px-6 text-center text-ivory-dim">
      {children}
    </div>
  );
}

function Blocked({ message }: { message: string }) {
  return (
    <Centered>
      <p className="font-bold text-ivory">{message}</p>
      <Link href="/" className="mt-4 rounded-2xl bg-gold px-6 py-3 font-extrabold text-ink">
        Retour à l&rsquo;accueil
      </Link>
    </Centered>
  );
}
