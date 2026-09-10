"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import FlightLayer from "@/components/FlightLayer";
import FxLayer from "@/components/FxLayer";
import { LoadingScreen } from "@/components/Loading";
import SettingsSheet from "@/components/SettingsSheet";
import { joinRoom } from "@/lib/api";
import type { GameMeta } from "@/lib/games";
import { tablePath } from "@/lib/games";
import {
  currentProfile,
  forgetTable,
  rememberTable,
  type StoredProfile,
} from "@/lib/identity";
import { applyFelt } from "@/lib/prefs";
import { preloadCards } from "@/lib/preloadCards";
import { preloadSounds } from "@/lib/sound";
import type { BaseRoomView } from "@/lib/types";
import type { RoomSocket } from "@/lib/useRoomSocket";

/* Le cadre d'une page de table, commun à tous les jeux : identité, prise de place,
   chargement des cartes et des sons avant tout affichage, connexion WebSocket,
   revanche, écran verrouillé, menu ⚙️, couche de vols, erreurs.
   Le jeu fournit son hook de socket, son lobby, sa table et ses règles. */

type Props<V extends BaseRoomView, S extends RoomSocket<V>> = {
  game: GameMeta;
  useSocket: (code: string, token: string | null) => S;
  lobby: (socket: S, view: V) => React.ReactNode;
  table: (socket: S, view: V) => React.ReactNode;
  rules: React.ReactNode;
  /* Chargements propres au jeu à attendre en plus des cartes et des sons communs. */
  preload?: () => Promise<unknown>;
};

export default function TableFrame<
  V extends BaseRoomView,
  S extends RoomSocket<V>,
>(props: Props<V, S>) {
  const { game, preload } = props;
  const { code } = useParams<{ code: string }>();
  const router = useRouter();
  const [profile, setProfile] = useState<StoredProfile | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joined, setJoined] = useState(false);
  // Cartes et sons chargés avant d'afficher quoi que ce soit : sur un réseau lent,
  // mieux vaut attendre un peu que voir des cartes blanches en pleine partie.
  const [assetsReady, setAssetsReady] = useState(false);

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
        rememberTable(game.slug, code);
        setJoined(true);
      })
      .catch((e) => {
        forgetTable(game.slug);
        setJoinError(
          e instanceof Error ? e.message : "Impossible de rejoindre.",
        );
      });
  }, [code, router, game.slug]);

  useEffect(() => {
    applyFelt();
    let cancelled = false;
    Promise.all([preloadCards(), preloadSounds(), preload?.()]).then(() => {
      if (!cancelled) setAssetsReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [preload]);

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

  if (joinError) return <Blocked game={game} message={joinError} />;
  if (!profile || !joined)
    return <LoadingScreen label="Connexion à la table…" />;
  if (!assetsReady) return <LoadingScreen label="On sort les cartes…" />;
  return <Room {...props} code={code} token={profile.token} />;
}

function Room<V extends BaseRoomView, S extends RoomSocket<V>>({
  game,
  useSocket,
  lobby,
  table,
  rules,
  code,
  token,
}: Props<V, S> & { code: string; token: string }) {
  const socket = useSocket(code, token);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const router = useRouter();

  const rematchCode = socket.rematchCode;
  useEffect(() => {
    // Quelqu'un a lancé la revanche : toute la table bascule sur la nouvelle partie.
    if (rematchCode) {
      rememberTable(game.slug, rematchCode);
      router.push(tablePath(game.slug, rematchCode));
    }
  }, [rematchCode, router, game.slug]);

  const finished = socket.view?.status === "finished";
  useEffect(() => {
    // Partie terminée : plus rien à reprendre depuis l'accueil (la revanche est une
    // nouvelle table, mémorisée à son tour).
    if (finished) forgetTable(game.slug);
  }, [finished, game.slug]);

  if (socket.closedReason)
    return <Blocked game={game} message={socket.closedReason} />;
  const view = socket.view;
  if (!view) return <LoadingScreen label="Connexion à la table…" />;
  const inLobby = view.status === "lobby";

  return (
    <main className="relative mx-auto flex h-full w-full max-w-md flex-col overflow-hidden">
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
          {lobby(socket, view)}
        </div>
      ) : (
        <div className="min-h-0 flex-1">{table(socket, view)}</div>
      )}

      <FxLayer />
      <FlightLayer />

      {settingsOpen && (
        <SettingsSheet
          game={game}
          code={view.code}
          inLobby={inLobby}
          rules={rules}
          onLeave={() => socket.leave()}
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

function GearIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-5 fill-none stroke-current stroke-2"
    >
      <circle cx="12" cy="12" r="3" />
      <path
        strokeLinecap="round"
        d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09c0 .68.4 1.29 1.03 1.56a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9c.27.63.88 1.03 1.56 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03Z"
      />
    </svg>
  );
}

export function Blocked({
  game,
  message,
}: {
  game: GameMeta;
  message: string;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center overflow-y-auto px-6 text-center text-ivory-dim">
      <p className="font-bold text-ivory">{message}</p>
      <Link
        href={game.path}
        className="mt-4 rounded-2xl bg-gold px-6 py-3 font-extrabold text-ink"
      >
        Retour à l&rsquo;accueil
      </Link>
    </div>
  );
}
