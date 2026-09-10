"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Avatar from "@/components/Avatar";
import { TransitionOverlay } from "@/components/Loading";
import { ApiError, createRoom, fetchMe, joinRoom } from "@/lib/api";
import { HUB_PATH, tablePath, type GameMeta } from "@/lib/games";
import { currentProfile, forgetTable, lastTable, type StoredProfile } from "@/lib/identity";
import { preloadCards } from "@/lib/preloadCards";
import { NO_STATS } from "@/lib/types";
import { useOpenRooms } from "@/lib/useOpenRooms";

/* L'accueil d'un jeu, commun à tous : créer une table, rejoindre par code, reprendre
   la dernière, tables ouvertes en direct. Le jeu fournit son en-tête (logo). */

export default function GameHome({ game, header }: { game: GameMeta; header: React.ReactNode }) {
  const router = useRouter();
  const [profile, setProfile] = useState<StoredProfile | null>(null);

  useEffect(() => {
    // Les cartes se chargent dès l'accueil : la table démarre avec tout en cache.
    preloadCards();
  }, []);

  useEffect(() => {
    const current = currentProfile();
    if (!current) {
      router.replace("/");
      return;
    }
    // Lecture localStorage impossible côté serveur : l'identité arrive après montage.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProfile(current);
  }, [router]);

  return (
    <main className="mx-auto flex min-h-0 w-full max-w-md grow flex-col overflow-y-auto px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-4">
      <Link
        href={HUB_PATH}
        className="mb-4 self-start rounded-xl py-2 pr-3 text-sm font-semibold text-ivory-dim/75 hover:text-ivory"
      >
        ‹ Tous les jeux
      </Link>
      {header}
      {profile && <Tables game={game} profile={profile} />}
    </main>
  );
}

function Tables({ game, profile }: { game: GameMeta; profile: StoredProfile }) {
  const router = useRouter();
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resumeCode, setResumeCode] = useState<string | null>(null);
  // Le voile de transition : posé dès le tap, retiré seulement en cas d'erreur
  // (en cas de succès on quitte l'écran, le voile reste jusqu'au changement de page).
  const [leaving, setLeaving] = useState<string | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setResumeCode(lastTable(game.slug));
  }, [game.slug]);

  const me = useQuery({ queryKey: ["me", profile.pseudo], queryFn: () => fetchMe(profile.token) });
  const rooms = useOpenRooms(game.slug);
  const stats = me.data?.stats[game.slug] ?? NO_STATS;

  const goToTable = ({ code }: { code: string }) => router.push(tablePath(game.slug, code));
  const fail = (e: unknown) => {
    setLeaving(null);
    setError(e instanceof ApiError ? e.message : "Le serveur est injoignable.");
  };
  const create = useMutation({
    mutationFn: () => createRoom(profile.token, game.slug),
    onMutate: () => {
      setError(null);
      setLeaving("Ouverture de ta table…");
    },
    onSuccess: goToTable,
    onError: fail,
  });
  const join = useMutation({
    mutationFn: (code: string) => joinRoom(profile.token, code),
    onMutate: (code) => {
      setError(null);
      setLeaving(`On te fait une place à la table ${code}…`);
    },
    onSuccess: goToTable,
    onError: fail,
  });
  const resume = useMutation({
    mutationFn: (code: string) => joinRoom(profile.token, code),
    onMutate: (code) => setLeaving(`Retour à la table ${code}…`),
    onSuccess: goToTable,
    onError: () => {
      // La partie n'existe plus : on oublie sans faire de bruit.
      setLeaving(null);
      forgetTable(game.slug);
      setResumeCode(null);
    },
  });
  const busy = leaving !== null;

  return (
    <section className="flex grow flex-col gap-6">
      <TransitionOverlay label={leaving} />
      <div className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
        <Avatar id={profile.avatar} size="lg" />
        <div className="grow">
          <p className="text-lg font-bold">{profile.pseudo}</p>
          {me.data && (
            <p className="text-sm text-ivory-dim/80">
              {stats.played} parties · {stats.won} gagnées · {stats.lost} perdues
            </p>
          )}
        </div>
      </div>

      {resumeCode && (
        <button
          type="button"
          onClick={() => resume.mutate(resumeCode)}
          disabled={busy}
          className="flex items-center justify-between rounded-2xl bg-felt-600 px-5 py-4 ring-1 ring-gold/50 enabled:active:translate-y-0.5"
        >
          <span className="font-extrabold">Reprendre la table {resumeCode}</span>
          <span className="text-gold">→</span>
        </button>
      )}

      <button
        type="button"
        onClick={() => create.mutate()}
        disabled={busy}
        className="rounded-2xl bg-gold py-5 text-xl font-extrabold text-ink shadow-card enabled:active:translate-y-0.5 disabled:opacity-40"
      >
        Créer une table
      </button>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (joinCode.length === 4) join.mutate(joinCode);
        }}
      >
        <input
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.replace(/\D/g, "").slice(0, 4))}
          inputMode="numeric"
          placeholder="Code de la table"
          className="grow rounded-xl bg-black/30 px-4 py-3 text-center text-lg font-bold tracking-[0.4em] text-ivory placeholder:font-normal placeholder:tracking-normal placeholder:text-ivory-dim/50 ring-1 ring-white/15 focus:outline-2 focus:outline-gold"
        />
        <button
          type="submit"
          disabled={joinCode.length !== 4 || busy}
          className="rounded-xl bg-felt-600 px-5 font-bold ring-1 ring-white/15 enabled:active:translate-y-0.5 disabled:opacity-40"
        >
          Rejoindre
        </button>
      </form>

      {error && <p className="text-sm text-card-red">{error}</p>}

      <div className="flex flex-col gap-2">
        <h2 className="font-bold">Tables ouvertes</h2>
        {rooms.rooms.length ? (
          rooms.rooms.map((room) => (
            <button
              key={room.code}
              type="button"
              disabled={busy}
              onClick={() => join.mutate(room.code)}
              className="flex items-center gap-2 rounded-2xl bg-black/25 p-3 text-left ring-1 ring-white/10 active:translate-y-0.5"
            >
              <span className="text-lg font-extrabold tracking-widest">{room.code}</span>
              <span className="ml-auto flex -space-x-2">
                {room.players.map((p) => (
                  <Avatar key={p.pseudo} id={p.avatar} size="sm" />
                ))}
              </span>
              <span className="text-sm text-ivory-dim/80">
                {room.seats_taken}/{room.seats_max}
              </span>
            </button>
          ))
        ) : rooms.ready ? (
          <p className="rounded-2xl border border-dashed border-ivory-dim/30 p-4 text-sm text-ivory-dim/70">
            Aucune table pour l&rsquo;instant. Crée la tienne et partage son code.
          </p>
        ) : (
          <p className="rounded-2xl border border-dashed border-ivory-dim/20 p-4 text-sm text-ivory-dim/50">
            On regarde qui joue…
          </p>
        )}
      </div>
    </section>
  );
}
