"use client";

import { createContext, useContext } from "react";
import { usePrefs, type BackStyle } from "@/lib/prefs";
import type { CardT } from "@/lib/types";

/* Le marquage au dos des cartes : chaque jeu pose le sien autour de sa table
   (« 9→1 » pour Nine to One, « G » pour le Goulag) ; ailleurs, la marque de la maison. */
export const CardBackLabel = createContext("✦");

/* Les faces viennent du deck « English pattern » de Dmitry Fomin (domaine public),
   servi depuis /public/cards — d'où les index J, Q, K, A repris dans toute l'interface. */
export function valueLabel(value: number): string {
  return { 11: "J", 12: "Q", 13: "K", 14: "A" }[value] ?? String(value);
}

const SUIT_GLYPH = {
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
  spades: "♠",
} as const;

/* Dos de cartes : motif choisi dans les paramètres, dessiné en CSS pur. */
const BACK_CSS: Record<BackStyle, React.CSSProperties> = {
  classic: {
    background:
      "repeating-linear-gradient(45deg, rgba(255,255,255,0.05) 0 3px, transparent 3px 9px), var(--color-felt-700)",
  },
  crimson: {
    background:
      "repeating-linear-gradient(45deg, rgba(255,255,255,0.07) 0 2px, transparent 2px 8px), repeating-linear-gradient(-45deg, rgba(255,255,255,0.07) 0 2px, transparent 2px 8px), #6e1f26",
  },
  royal: {
    background:
      "radial-gradient(rgba(255,255,255,0.14) 1px, transparent 1.5px) 0 0 / 8px 8px, #1c2f55",
  },
};

const SIZES = {
  xxs: { w: "w-5", radius: "rounded-[3px]", back: "text-[6px]", idx: "" },
  xs: { w: "w-6", radius: "rounded-[3px]", back: "text-[6px]", idx: "" },
  sm: { w: "w-9", radius: "rounded", back: "text-[8px]", idx: "text-[8px]" },
  md: {
    w: "w-14",
    radius: "rounded-md",
    back: "text-[10px]",
    idx: "text-[11px]",
  },
  lg: {
    w: "w-[4.5rem]",
    radius: "rounded-lg",
    back: "text-sm",
    idx: "text-[13px]",
  },
} as const;

type Props = {
  card?: CardT;
  faceDown?: boolean;
  size?: keyof typeof SIZES;
  highlighted?: boolean;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  className?: string;
};

export default function PlayingCard({
  card,
  faceDown = false,
  size = "md",
  highlighted = false,
  selected = false,
  disabled = false,
  onClick,
  className = "",
}: Props) {
  const s = SIZES[size];
  const { back } = usePrefs();
  const backLabel = useContext(CardBackLabel);
  const interactive = Boolean(onClick) && !disabled;

  const base = `${s.w} aspect-[2/3] ${s.radius} shrink-0 select-none transition-transform duration-150 ${className}`;
  const ring = selected
    ? "ring-2 ring-gold -translate-y-2"
    : highlighted
      ? "ring-2 ring-gold/80 shadow-[0_0_14px_rgba(229,181,74,0.45)]"
      : "";

  if (faceDown || !card) {
    // En minuscule, le dos se fond dans le tapis : bord clair pour rester visible.
    const border =
      size === "xs" || size === "xxs" ? "border-white/30" : "border-black/40";
    return (
      <Wrapper interactive={interactive} onClick={onClick} disabled={disabled}>
        <span
          className={`${base} ${ring} block border ${border} shadow-card-flat`}
          style={BACK_CSS[back]}
        >
          {size !== "xs" && size !== "xxs" && (
            <span className="flex h-full items-center justify-center">
              <span
                className={`${s.back} rounded border border-gold/50 px-1 font-bold text-gold/80`}
              >
                {backLabel}
              </span>
            </span>
          )}
        </span>
      </Wrapper>
    );
  }

  // En tailles minuscules (plateaux adverses), l'artwork est illisible : valeur + symbole.
  if (size === "xs" || size === "xxs") {
    const red = card.suit === "hearts" || card.suit === "diamonds";
    const text = size === "xs" ? "text-[10px]" : "text-[9px]";
    const glyph = size === "xs" ? "text-[9px]" : "text-[8px]";
    return (
      <span
        className={`${base} ${ring} flex flex-col items-center justify-center bg-white leading-none shadow-card-flat ${
          red ? "text-card-red" : "text-ink"
        }`}
      >
        <span className={`${text} font-extrabold`}>
          {valueLabel(card.value)}
        </span>
        <span className={glyph}>{SUIT_GLYPH[card.suit]}</span>
      </span>
    );
  }

  const red = card.suit === "hearts" || card.suit === "diamonds";
  return (
    <Wrapper interactive={interactive} onClick={onClick} disabled={disabled}>
      <span
        className={`${base} ${ring} block overflow-hidden bg-white shadow-card-flat`}
      >
        {/* Contexte de positionnement interne : le span externe garde la classe
            de position (absolute…) que l'appelant lui donne. */}
        <span className="relative block h-full w-full">
          {/* Sous-couche : valeur + couleur, visibles le temps que l'image arrive.
              Jamais de carte blanche, même sur un réseau lent. */}
          <span
            aria-hidden
            className={`absolute left-[5px] top-[3px] leading-none ${s.idx} font-extrabold ${
              red ? "text-card-red" : "text-ink"
            }`}
          >
            {valueLabel(card.value)}
            <span className="block">{SUIT_GLYPH[card.suit]}</span>
          </span>
          {/* Rendu à 200 % puis réduit de moitié : le SVG est rastérisé plus grand,
              les contours restent nets même en petit et sous rotation. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`/cards/${card.value}-${card.suit}.svg`}
            alt={`${valueLabel(card.value)} ${card.suit}`}
            className="relative block max-w-none origin-top-left scale-50"
            style={{ width: "200%", height: "200%" }}
            draggable={false}
          />
        </span>
      </span>
    </Wrapper>
  );
}

function Wrapper({
  interactive,
  onClick,
  disabled,
  children,
}: {
  interactive: boolean;
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  if (!onClick) return <>{children}</>;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || !interactive}
      className="focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold disabled:cursor-default"
    >
      {children}
    </button>
  );
}
