"use client";

import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Avatar from "@/components/Avatar";
import { leaderboardPath } from "@/components/Leaderboard";
import { LoadingScreen } from "@/components/Loading";
import PlayingCard, { CardBackLabel } from "@/components/PlayingCard";
import { fetchMe } from "@/lib/api";
import { GAMES, type GameMeta } from "@/lib/games";
import { currentProfile, signOut, type StoredProfile } from "@/lib/identity";
import { preloadCards } from "@/lib/preloadCards";
import type { GameStats } from "@/lib/types";

/* La sélection des jeux : une tuile par jeu, posée sur le tapis comme un plateau.
   Les cartes de chaque tuile sont les vraies cartes du jeu, disposées comme on
   les trouve sur sa table — c'est ce qui distingue un jeu d'un autre au premier
   coup d'œil, pas une icône. */

export default function Page() {
  const router = useRouter();
  const [profile, setProfile] = useState<StoredProfile | null>(null);

  useEffect(() => {
    preloadCards();
  }, []);

  useEffect(() => {
    const current = currentProfile();
    if (!current) {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProfile(current);
  }, [router]);

  const me = useQuery({
    queryKey: ["me", profile?.pseudo],
    queryFn: () => fetchMe(profile!.token),
    enabled: profile !== null,
  });

  if (!profile) return <LoadingScreen label="Un instant…" />;

  return (
    <main className="mx-auto flex min-h-0 w-full max-w-md grow flex-col overflow-y-auto px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-6">
      <header className="mb-6 flex items-center gap-3">
        <Avatar id={profile.avatar} size="lg" />
        <div className="min-w-0 grow">
          <p className="truncate text-lg font-bold">{profile.pseudo}</p>
          <p className="text-sm text-ivory-dim/75">À quoi on joue ?</p>
        </div>
        <button
          type="button"
          onClick={() => {
            signOut();
            router.replace("/");
          }}
          className="rounded-xl px-3 py-2 text-sm text-ivory-dim/70 hover:text-ivory"
        >
          Changer
        </button>
      </header>

      <ul className="flex flex-col gap-4">
        {GAMES.map((game, i) => (
          <li key={game.slug}>
            <GameTile game={game} index={i} stats={me.data?.stats[game.slug]} />
          </li>
        ))}
      </ul>

      <Link
        href={leaderboardPath(null)}
        className="mt-6 flex items-center justify-between rounded-2xl bg-black/25 px-5 py-4 ring-1 ring-white/10 active:translate-y-0.5"
      >
        <span>
          <span className="block font-extrabold">Classement général</span>
          <span className="block text-sm text-ivory-dim/75">
            Toutes les victoires, tous les jeux.
          </span>
        </span>
        <span className="text-gold">→</span>
      </Link>
    </main>
  );
}

function GameTile({
  game,
  index,
  stats,
}: {
  game: GameMeta;
  index: number;
  stats?: GameStats;
}) {
  const body = (
    <div
      className={`relative flex min-h-[11rem] items-end overflow-hidden rounded-3xl p-5 shadow-card ring-1 ring-white/10 ${
        game.available ? "" : "opacity-80"
      }`}
      style={{ background: game.mat }}
    >
      {/* Lumière rasante : la tuile est un tapis éclairé, pas un aplat. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(160deg,rgba(255,255,255,0.08),transparent_45%)]"
      />
      <div className="relative z-10 flex flex-col gap-1 pr-28">
        <h2 className="text-3xl font-extrabold leading-none tracking-tight">
          {game.name}
        </h2>
        <p className="text-sm font-semibold text-ivory-dim/85">
          {game.players}
        </p>
        <p className="mt-1 text-sm leading-snug text-ivory-dim/80">
          {game.tagline}
        </p>
        {game.available ? (
          stats && stats.played > 0 ? (
            <p className="mt-2 text-xs font-semibold text-gold/90">
              {stats.played} {stats.played > 1 ? "parties" : "partie"},{" "}
              {stats.won} {stats.won > 1 ? "gagnées" : "gagnée"}
            </p>
          ) : (
            <p className="mt-2 text-xs font-semibold text-gold/90">Jouer</p>
          )
        ) : (
          <p className="mt-2 text-xs font-semibold text-ivory-dim/70">
            Bientôt
          </p>
        )}
      </div>
      <CardBackLabel.Provider value={game.slug === "nine-to-one" ? "9→1" : "G"}>
        <Illustration slug={game.slug} index={index} />
      </CardBackLabel.Provider>
    </div>
  );

  if (!game.available) return <div aria-disabled>{body}</div>;
  return (
    <Link
      href={game.path}
      className="block rounded-3xl transition-transform active:translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold"
    >
      {body}
    </Link>
  );
}

/* Les cartes de chaque jeu, posées de travers en haut à droite de la tuile, et qui
   se déploient en éventail à l'arrivée sur la page — le seul mouvement de l'écran. */
function Illustration({ slug, index }: { slug: string; index: number }) {
  const reduced = useReducedMotion();
  const spring = { type: "spring" as const, stiffness: 260, damping: 24 };
  const cards =
    slug === "nine-to-one"
      ? [
          {
            card: { value: 9, suit: "spades" as const },
            x: 0,
            y: 6,
            rotate: -14,
          },
          {
            card: { value: 14, suit: "hearts" as const },
            x: 34,
            y: 0,
            rotate: 10,
          },
        ]
      : [
          {
            card: { value: 13, suit: "spades" as const },
            x: 0,
            y: 6,
            rotate: -12,
          },
          {
            card: { value: 7, suit: "hearts" as const },
            x: 22,
            y: 0,
            rotate: 2,
          },
          { faceDown: true, x: 46, y: 8, rotate: 16 },
        ];
  return (
    <div aria-hidden className="absolute right-5 top-4 h-24 w-[6.5rem]">
      {cards.map((c, i) => (
        <motion.span
          key={i}
          className="absolute left-0 top-0"
          initial={reduced ? false : { x: 18, y: 8, rotate: 0, opacity: 0 }}
          animate={{ x: c.x, y: c.y, rotate: c.rotate, opacity: 1 }}
          transition={{ ...spring, delay: 0.15 + index * 0.12 + i * 0.07 }}
        >
          {"faceDown" in c ? (
            <PlayingCard faceDown size="md" />
          ) : (
            <PlayingCard card={c.card} size="md" />
          )}
        </motion.span>
      ))}
    </div>
  );
}
