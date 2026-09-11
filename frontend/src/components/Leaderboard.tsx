"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Avatar from "@/components/Avatar";
import { LoadingScreen, ShufflingCards } from "@/components/Loading";
import { fetchLeaderboard } from "@/lib/api";
import { GAMES, HUB_PATH, type GameMeta } from "@/lib/games";
import { currentProfile, type StoredProfile } from "@/lib/identity";
import type { LeaderboardEntry } from "@/lib/types";

/* Le classement, d'un jeu ou de tous les jeux cumulés. Les trois premiers montent
   sur le podium, les autres suivent en liste, page après page, jusqu'à la lanterne
   rouge. La place du joueur est rappelée en tête, quelle que soit sa profondeur. */

export function leaderboardPath(game: string | null): string {
  return game ? `/${game}/leaderboard` : `${HUB_PATH}/leaderboard`;
}

export default function Leaderboard({ game }: { game: GameMeta | null }) {
  const router = useRouter();
  const [profile, setProfile] = useState<StoredProfile | null>(null);

  useEffect(() => {
    const current = currentProfile();
    if (!current) {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProfile(current);
  }, [router]);

  return (
    <main className="mx-auto flex min-h-0 w-full max-w-md grow flex-col overflow-y-auto px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-4">
      <Link
        href={game ? game.path : HUB_PATH}
        className="mb-4 self-start rounded-xl py-2 pr-3 text-sm font-semibold text-ivory-dim/75 hover:text-ivory"
      >
        ‹ {game ? game.name : "Tous les jeux"}
      </Link>

      <nav
        aria-label="Classement par jeu"
        className="mb-6 flex rounded-full bg-black/30 p-1 ring-1 ring-white/10"
      >
        <Tab href={leaderboardPath(null)} active={game === null}>
          Tous
        </Tab>
        {GAMES.filter((g) => g.available).map((g) => (
          <Tab key={g.slug} href={leaderboardPath(g.slug)} active={game?.slug === g.slug}>
            {g.name}
          </Tab>
        ))}
      </nav>

      {profile && <Ranking game={game} profile={profile} />}
    </main>
  );
}

function Tab({ href, active, children }: { href: string; active: boolean; children: string }) {
  return (
    <Link
      href={href}
      replace
      aria-current={active ? "page" : undefined}
      className={`flex-1 rounded-full py-2 text-center text-sm font-bold transition-colors ${
        active ? "bg-gold text-ink shadow-card" : "text-ivory-dim/75 active:text-ivory"
      }`}
    >
      {children}
    </Link>
  );
}

function Ranking({ game, profile }: { game: GameMeta | null; profile: StoredProfile }) {
  const slug = game?.slug ?? null;
  const pages = useInfiniteQuery({
    queryKey: ["leaderboard", slug, profile.pseudo],
    queryFn: ({ pageParam }) => fetchLeaderboard(slug, pageParam, profile.pseudo),
    initialPageParam: 0,
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.entries.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });

  // Le bas de liste réclame la page suivante dès qu'il approche de l'écran.
  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = pages;
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasNextPage) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetchingNextPage) fetchNextPage();
      },
      { rootMargin: "240px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (pages.isPending) return <LoadingScreen label="On compte les points…" />;
  if (pages.isError) {
    return (
      <div className="flex flex-col items-center gap-4 py-10 text-center">
        <p className="text-sm text-card-red">Le classement n&rsquo;est pas arrivé.</p>
        <button
          type="button"
          onClick={() => pages.refetch()}
          className="rounded-xl bg-felt-600 px-5 py-3 font-bold ring-1 ring-white/15 active:translate-y-0.5"
        >
          Réessayer
        </button>
      </div>
    );
  }

  const first = pages.data.pages[0];
  const entries = pages.data.pages.flatMap((p) => p.entries);
  const me = first.me;
  const total = first.total;

  if (total === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-ivory-dim/30 p-5 text-center text-sm leading-relaxed text-ivory-dim/70">
        Personne n&rsquo;est encore classé{game ? ` au ${game.name}` : ""}.
        <br />
        La première partie ouvre le bal.
      </p>
    );
  }

  const podium = entries.slice(0, 3);
  const rest = entries.slice(3);
  const complete = !hasNextPage;

  return (
    <section className="flex flex-col gap-5">
      <Podium entries={podium} me={me} />

      <MyPlace me={me} total={total} game={game} />

      {rest.length > 0 && (
        <ol className="flex flex-col gap-2">
          {rest.map((entry) => (
            <Row
              key={entry.id}
              entry={entry}
              mine={me?.id === entry.id}
              last={complete && entry.rank === total}
            />
          ))}
        </ol>
      )}

      <div ref={sentinel} className="flex min-h-12 flex-col items-center justify-center gap-2">
        {isFetchingNextPage ? (
          <>
            <ShufflingCards />
            <p className="text-sm text-ivory-dim/70">On compte les points…</p>
          </>
        ) : complete ? (
          <p className="text-sm text-ivory-dim/55">
            {total} {total > 1 ? "joueurs classés" : "joueur classé"}
          </p>
        ) : null}
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------------- */
/* Podium                                                                  */
/* ----------------------------------------------------------------------- */

const MEDALS = ["#e5b54a", "#cfd3d8", "#c98552"] as const;

function Podium({ entries, me }: { entries: LeaderboardEntry[]; me: LeaderboardEntry | null }) {
  const reduced = useReducedMotion();
  // Le premier au centre, plus haut ; le deuxième à sa gauche, le troisième à sa droite.
  const order = [1, 0, 2];
  const heights = ["h-24", "h-16", "h-11"];
  return (
    <ol className="flex items-end gap-2" aria-label="Les trois premiers">
      {order.map((i) => {
        const entry = entries[i];
        const medal = MEDALS[i];
        return (
          <motion.li
            key={i}
            className="flex flex-1 flex-col items-center"
            initial={reduced ? false : { y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{
              type: "spring",
              stiffness: 220,
              damping: 22,
              delay: 0.1 + [0.25, 0, 0.4][i],
            }}
          >
            {entry ? (
              <>
                <span
                  className={`rounded-full ${i === 0 ? "p-1" : "p-0.5"}`}
                  style={{
                    background: medal,
                    boxShadow: i === 0 ? `0 0 24px 4px ${medal}66` : undefined,
                  }}
                >
                  <Avatar id={entry.avatar} size={i === 0 ? "xl" : "lg"} />
                </span>
                <p
                  className={`mt-2 w-full truncate text-center font-extrabold ${
                    i === 0 ? "text-base" : "text-sm"
                  } ${me?.id === entry.id ? "text-gold" : ""}`}
                >
                  {entry.pseudo}
                </p>
                <p className="text-xs text-ivory-dim/70">
                  <span className="font-bold text-ivory">{entry.won}</span>{" "}
                  {entry.won > 1 ? "victoires" : "victoire"}
                </p>
              </>
            ) : (
              <>
                <span className="size-16 rounded-full border-2 border-dashed border-ivory-dim/25" />
                <p className="mt-2 text-sm font-bold text-ivory-dim/45">Libre</p>
                <p className="text-xs text-ivory-dim/40">à prendre</p>
              </>
            )}
            <div
              className={`mt-2 flex w-full ${heights[i]} items-start justify-center rounded-t-2xl pt-2 ring-1 ring-white/10`}
              style={{
                background: `linear-gradient(180deg, ${medal}33, ${medal}0d)`,
                boxShadow: `inset 0 2px 0 ${medal}80`,
              }}
            >
              <span
                className="text-2xl font-extrabold leading-none tabular-nums"
                style={{ color: medal }}
              >
                {i + 1}
              </span>
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}

/* ----------------------------------------------------------------------- */
/* Ma place                                                                */
/* ----------------------------------------------------------------------- */

function MyPlace({
  me,
  total,
  game,
}: {
  me: LeaderboardEntry | null;
  total: number;
  game: GameMeta | null;
}) {
  if (!me) {
    return (
      <p className="rounded-2xl bg-black/25 px-4 py-3 text-sm text-ivory-dim/75 ring-1 ring-white/10">
        Tu n&rsquo;es pas encore classé{game ? ` au ${game.name}` : ""}. Une partie suffit.
      </p>
    );
  }
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-felt-600/60 px-4 py-3 ring-1 ring-gold/60">
      <span className="text-2xl font-extrabold tabular-nums text-gold">{me.rank}</span>
      <span className="text-sm text-ivory-dim/60">/ {total}</span>
      <div className="min-w-0 grow">
        <p className="truncate text-sm font-bold">Ta place</p>
        <WinBar entry={me} />
      </div>
      <Score entry={me} />
    </div>
  );
}

/* ----------------------------------------------------------------------- */
/* Lignes du classement                                                    */
/* ----------------------------------------------------------------------- */

function Row({ entry, mine, last }: { entry: LeaderboardEntry; mine: boolean; last: boolean }) {
  return (
    <li
      className={`flex items-center gap-3 rounded-2xl p-3 ring-1 ${
        mine ? "bg-felt-600/60 ring-gold/60" : "bg-black/25 ring-white/10"
      }`}
    >
      <span className="w-7 shrink-0 text-right text-base font-extrabold tabular-nums text-ivory-dim/55">
        {entry.rank}
      </span>
      <Avatar id={entry.avatar} />
      <div className="min-w-0 grow">
        <p className={`truncate font-bold ${mine ? "text-gold" : ""}`}>
          {entry.pseudo}
          {last && (
            <span className="ml-2 rounded-full bg-card-red/20 px-2 py-0.5 text-[0.65rem] font-bold text-card-red ring-1 ring-card-red/40">
              Lanterne rouge
            </span>
          )}
        </p>
        <WinBar entry={entry} />
      </div>
      <Score entry={entry} />
    </li>
  );
}

/* Part de victoires sur les parties jouées : un trait, pas un pourcentage à lire. */
function WinBar({ entry }: { entry: LeaderboardEntry }) {
  const ratio = entry.played ? entry.won / entry.played : 0;
  return (
    <span
      className="mt-1.5 block h-1 w-full overflow-hidden rounded-full bg-white/10"
      role="img"
      aria-label={`${Math.round(ratio * 100)} % de victoires`}
    >
      <span
        className="block h-full rounded-full bg-gold"
        style={{ width: `${Math.max(ratio * 100, entry.won ? 4 : 0)}%` }}
      />
    </span>
  );
}

function Score({ entry }: { entry: LeaderboardEntry }) {
  return (
    <div className="shrink-0 text-right">
      <p className="text-xl font-extrabold leading-none tabular-nums">{entry.won}</p>
      <p className="mt-1 text-xs text-ivory-dim/60 tabular-nums">
        sur {entry.played} {entry.played > 1 ? "parties" : "partie"}
      </p>
    </div>
  );
}
