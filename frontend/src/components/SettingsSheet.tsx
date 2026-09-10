"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sheet } from "@/components/Sheet";
import type { GameMeta } from "@/lib/games";
import { forgetTable } from "@/lib/identity";
import {
  BACK_STYLES,
  FELT_STYLES,
  setPref,
  usePrefs,
  type BackStyle,
  type FeltStyle,
} from "@/lib/prefs";
import { isMuted, setMuted } from "@/lib/sound";

/* Le menu ⚙️ d'une table, commun à tous les jeux : sons, dos des cartes, tapis,
   règles (fournies par le jeu), quitter. */

export default function SettingsSheet({
  game,
  code,
  inLobby,
  rules,
  onLeave,
  onClose,
}: {
  game: GameMeta;
  code: string;
  inLobby: boolean;
  rules: React.ReactNode;
  onLeave: () => void;
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

  if (showRules) return <Sheet onClose={() => setShowRules(false)}>{rules}</Sheet>;

  return (
    <Sheet onClose={onClose}>
      <h2 className="mb-4 text-center text-lg font-extrabold">
        Table <span className="tracking-widest text-gold">{code}</span>
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
            onLeave();
            if (inLobby) forgetTable(game.slug);
            router.push(game.path);
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
