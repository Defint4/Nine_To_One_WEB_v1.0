"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Avatar from "@/components/Avatar";
import { ShufflingCards } from "@/components/Loading";
import { ApiError, enter } from "@/lib/api";
import { GALLERY } from "@/lib/avatars";
import { APP_NAME, HUB_PATH } from "@/lib/games";
import {
  currentProfile,
  forgetProfile,
  listProfiles,
  saveProfile,
  type StoredProfile,
} from "@/lib/identity";

/* L'entrée de la plateforme : qui joue ? Un pseudo et un avatar, mémorisés sur
   l'appareil. Une fois identifié, on va à la sélection des jeux. */

const AFTER_ENTER = HUB_PATH;

type Screen =
  | { name: "loading" }
  | { name: "choose"; profiles: StoredProfile[] }
  | { name: "create" };

export default function Page() {
  const router = useRouter();
  const [screen, setScreen] = useState<Screen>({ name: "loading" });

  useEffect(() => {
    // La sélection des jeux est la page suivante dans tous les cas : on la précharge.
    router.prefetch(AFTER_ENTER);
    if (currentProfile()) {
      router.replace(AFTER_ENTER);
      return;
    }
    const profiles = listProfiles();
    // Lecture localStorage impossible côté serveur : l'écran se décide après montage.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setScreen(profiles.length ? { name: "choose", profiles } : { name: "create" });
  }, [router]);

  return (
    <main className="mx-auto flex min-h-0 w-full max-w-md grow flex-col overflow-y-auto px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-10">
      <header className="mb-10 flex flex-col items-center">
        <h1 className="text-4xl font-extrabold tracking-tight">{APP_NAME}</h1>
        <p className="mt-1 text-sm text-ivory-dim/80">Des jeux entre amis, sur le téléphone.</p>
      </header>
      {screen.name === "loading" && (
        <div className="flex flex-col items-center gap-4 pt-6 text-ivory-dim">
          <ShufflingCards />
          <p className="text-sm">Un instant…</p>
        </div>
      )}
      {screen.name === "choose" && (
        <ChooseProfile
          profiles={screen.profiles}
          onDone={() => router.replace(AFTER_ENTER)}
          onNew={() => setScreen({ name: "create" })}
        />
      )}
      {screen.name === "create" && <CreateProfile onDone={() => router.replace(AFTER_ENTER)} />}
    </main>
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
