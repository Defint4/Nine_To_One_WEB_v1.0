"use client";

/* Préférences visuelles de l'appareil : dos des cartes et couleur du tapis.
   Purement cosmétique et local — chacun voit la table à son goût. */

import { useSyncExternalStore } from "react";

export type BackStyle = "classic" | "crimson" | "royal";
export type FeltStyle = "green" | "navy" | "wine";

export const BACK_STYLES: Record<BackStyle, string> = {
  classic: "Vert rayé",
  crimson: "Rouge losanges",
  royal: "Bleu pointillé",
};

export const FELT_STYLES: Record<FeltStyle, string> = {
  green: "Tapis vert",
  navy: "Tapis nuit",
  wine: "Tapis bordeaux",
};

const KEY = "games:prefs";

type Prefs = { back: BackStyle; felt: FeltStyle };
const DEFAULTS: Prefs = { back: "classic", felt: "green" };

let cache: Prefs | null = null;
const listeners = new Set<() => void>();

function read(): Prefs {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(KEY);
    cache = raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) } : DEFAULTS;
  } catch {
    cache = DEFAULTS;
  }
  return cache ?? DEFAULTS;
}

export function getPrefs(): Prefs {
  return typeof window === "undefined" ? DEFAULTS : read();
}

export function setPref<K extends keyof Prefs>(key: K, value: Prefs[K]) {
  cache = { ...read(), [key]: value };
  try {
    localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    /* stockage indisponible */
  }
  applyFelt();
  for (const listener of listeners) listener();
}

export function usePrefs(): Prefs {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getPrefs,
    () => DEFAULTS
  );
}

/* Le tapis se pilote en CSS via un attribut sur <html> (voir globals.css). */
export function applyFelt() {
  if (typeof document !== "undefined") {
    document.documentElement.dataset.felt = getPrefs().felt;
  }
}
