"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Avatar from "@/components/Avatar";
import PlayingCard from "@/components/PlayingCard";
import { ApiError, createRoom, enter, fetchMe, joinRoom, listRooms } from "@/lib/api";
import { GALLERY } from "@/lib/avatars";
import { preloadCards } from "@/lib/preloadCards";
import {
  currentProfile,
  forgetProfile,
  forgetTable,
  lastTable,
  listProfiles,
  saveProfile,
  signOut,
  type StoredProfile,
} from "@/lib/identity";

type Screen =
  | { name: "loading" }
  | { name: "choose"; profiles: StoredProfile[] }
  | { name: "create" }
  | { name: "home"; profile: StoredProfile };

export default function Page() {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });

  useEffect(() => {
    // Les cartes se chargent dès l'accueil : la table démarre avec tout en cache.
    preloadCards();
  }, []);

  useEffect(() => {
    const current = currentProfile();
    const profiles = listProfiles();
    // Lecture localStorage impossible côté serveur : l'écran se décide après montage.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setScreen(
      current
        ? { name: "home", profile: current }
        : profiles.length
          ? { name: "choose", profiles }
          : { name: "create" }
    );
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-md grow flex-col px-5 pb-8 pt-10">
      <Wordmark compact={screen.name === "home"} />
      {screen.name === "choose" && (
        <ChooseProfile
          profiles={screen.profiles}
          onDone={(profile) => setScreen({ name: "home", profile })}
          onNew={() => setScreen({ name: "create" })}
        />
      )}
      {screen.name === "create" && (
        <CreateProfile onDone={(profile) => setScreen({ name: "home", profile })} />
      )}
      {screen.name === "home" && (
        <Home
          profile={screen.profile}
          onSignOut={() => {
            signOut();
            const profiles = listProfiles();
            setScreen(profiles.length ? { name: "choose", profiles } : { name: "create" });
          }}
        />
      )}
    </main>
  );
}

function Wordmark({ compact }: { compact: boolean }) {
  // Les cartes md font 84 px de haut (w-14, ratio 2/3) : le conteneur doit les
  // absorber, rotation comprise, pour que l'as ne déborde pas sur le titre.
  return (
    <header className={`flex flex-col items-center ${compact ? "mb-6" : "mb-10"}`}>
      <div className={`relative ${compact ? "mb-2 h-16 w-20" : "mb-3 h-[6.2rem] w-28"}`}>
        <PlayingCard
          card={{ value: 9, suit: "spades" }}
          size={compact ? "sm" : "md"}
          className="absolute left-1 top-1 -rotate-12"
        />
        <PlayingCard
          card={{ value: 14, suit: "hearts" }}
          size={compact ? "sm" : "md"}
          className={`absolute rotate-12 ${compact ? "left-7 top-0" : "left-10 top-0"}`}
        />
      </div>
      <h1 className={`font-extrabold tracking-tight ${compact ? "text-2xl" : "text-4xl"}`}>
        Nine to One
      </h1>
      {!compact && <p className="mt-1 text-sm text-ivory-dim/80">La table est ouverte.</p>}
    </header>
  );
}

function ChooseProfile({
  profiles,
  onDone,
  onNew,
}: {
  profiles: StoredProfile[];
  onDone: (profile: StoredProfile) => void;
  onNew: () => void;
}) {
  const [items, setItems] = useState(profiles);
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">Qui joue ?</h2>
      {items.map((profile) => (
        <div
          key={profile.pseudo}
          className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10"
        >
          <button
            type="button"
            className="flex grow items-center gap-3 text-left"
            onClick={() => {
              saveProfile(profile);
              onDone(profile);
            }}
          >
            <Avatar id={profile.avatar} size="lg" />
            <span className="text-lg font-bold">{profile.pseudo}</span>
          </button>
          <button
            type="button"
            aria-label={`Oublier ${profile.pseudo}`}
            className="rounded-full px-3 py-2 text-ivory-dim/60 hover:text-ivory"
            onClick={() => {
              forgetProfile(profile.pseudo);
              const rest = items.filter((p) => p.pseudo !== profile.pseudo);
              setItems(rest);
              if (!rest.length) onNew();
            }}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={onNew}
        className="mt-2 rounded-2xl border border-dashed border-ivory-dim/40 p-4 font-bold text-ivory-dim hover:text-ivory"
      >
        Nouveau joueur
      </button>
    </section>
  );
}

function CreateProfile({ onDone }: { onDone: (profile: StoredProfile) => void }) {
  const [pseudo, setPseudo] = useState("");
  const [avatar, setAvatar] = useState(GALLERY[0]);
  const mutation = useMutation({
    mutationFn: () => enter(pseudo.trim(), avatar),
    onSuccess: ({ token }) => {
      const profile = { pseudo: pseudo.trim(), avatar, token };
      saveProfile(profile);
      onDone({ ...profile, lastUsed: Date.now() });
    },
  });

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (pseudo.trim().length >= 2) mutation.mutate();
      }}
    >
      <label className="flex flex-col gap-2">
        <span className="font-bold">Ton pseudo</span>
        <input
          value={pseudo}
          onChange={(e) => setPseudo(e.target.value)}
          maxLength={20}
          autoFocus
          placeholder="2 à 20 caractères"
          className="rounded-xl bg-black/30 px-4 py-3 text-lg font-bold text-ivory placeholder:font-normal placeholder:text-ivory-dim/50 ring-1 ring-white/15 focus:outline-2 focus:outline-gold"
        />
      </label>
      <div className="flex flex-col gap-2">
        <span className="font-bold">Ton avatar</span>
        <div className="grid grid-cols-6 gap-2">
          {GALLERY.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setAvatar(id)}
              className={`rounded-full p-0.5 ${id === avatar ? "ring-2 ring-gold" : ""}`}
            >
              <Avatar id={id} size="md" />
            </button>
          ))}
        </div>
      </div>
      {mutation.error && (
        <p className="text-sm text-card-red">
          {mutation.error instanceof ApiError
            ? mutation.error.message
            : "Le serveur est injoignable. Réessaie dans un instant."}
        </p>
      )}
      <button
        type="submit"
        disabled={pseudo.trim().length < 2 || mutation.isPending}
        className="rounded-2xl bg-gold py-4 text-lg font-extrabold text-ink shadow-card enabled:active:translate-y-0.5 disabled:opacity-40"
      >
        {mutation.isPending ? "Un instant…" : "Entrer"}
      </button>
    </form>
  );
}

function Home({ profile, onSignOut }: { profile: StoredProfile; onSignOut: () => void }) {
  const router = useRouter();
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resumeCode, setResumeCode] = useState<string | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setResumeCode(lastTable());
  }, []);

  const me = useQuery({ queryKey: ["me", profile.pseudo], queryFn: () => fetchMe(profile.token) });
  const rooms = useQuery({ queryKey: ["rooms"], queryFn: listRooms, refetchInterval: 4000 });

  const create = useMutation({
    mutationFn: () => createRoom(profile.token),
    onSuccess: ({ code }) => router.push(`/table/${code}`),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Le serveur est injoignable."),
  });
  const join = useMutation({
    mutationFn: (code: string) => joinRoom(profile.token, code),
    onSuccess: ({ code }) => router.push(`/table/${code}`),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Le serveur est injoignable."),
  });
  const resume = useMutation({
    mutationFn: (code: string) => joinRoom(profile.token, code),
    onSuccess: ({ code }) => router.push(`/table/${code}`),
    onError: () => {
      // La partie n'existe plus : on oublie sans faire de bruit.
      forgetTable();
      setResumeCode(null);
    },
  });

  return (
    <section className="flex grow flex-col gap-6">
      <div className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
        <Avatar id={profile.avatar} size="lg" />
        <div className="grow">
          <p className="text-lg font-bold">{profile.pseudo}</p>
          {me.data && (
            <p className="text-sm text-ivory-dim/80">
              {me.data.games_played} parties · {me.data.games_won} gagnées ·{" "}
              {me.data.games_lost} perdues
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onSignOut}
          className="rounded-xl px-3 py-2 text-sm text-ivory-dim/70 hover:text-ivory"
        >
          Changer
        </button>
      </div>

      {resumeCode && (
        <button
          type="button"
          onClick={() => resume.mutate(resumeCode)}
          disabled={resume.isPending}
          className="flex items-center justify-between rounded-2xl bg-felt-600 px-5 py-4 ring-1 ring-gold/50 enabled:active:translate-y-0.5"
        >
          <span className="font-extrabold">Reprendre la table {resumeCode}</span>
          <span className="text-gold">→</span>
        </button>
      )}

      <button
        type="button"
        onClick={() => create.mutate()}
        disabled={create.isPending}
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
          disabled={joinCode.length !== 4 || join.isPending}
          className="rounded-xl bg-felt-600 px-5 font-bold ring-1 ring-white/15 enabled:active:translate-y-0.5 disabled:opacity-40"
        >
          Rejoindre
        </button>
      </form>

      {error && <p className="text-sm text-card-red">{error}</p>}

      <div className="flex flex-col gap-2">
        <h2 className="font-bold">Tables ouvertes</h2>
        {rooms.data?.length ? (
          rooms.data.map((room) => (
            <button
              key={room.code}
              type="button"
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
        ) : (
          <p className="rounded-2xl border border-dashed border-ivory-dim/30 p-4 text-sm text-ivory-dim/70">
            Aucune table pour l&rsquo;instant. Crée la tienne et partage son code.
          </p>
        )}
      </div>
    </section>
  );
}
