"use client";

import { AnimatePresence, motion } from "motion/react";
import PlayingCard from "@/components/PlayingCard";

/* Les écrans d'attente de la plateforme. Un seul motif partout — deux cartes qui se
   battent — pour que passer d'un écran à l'autre ne casse jamais le mouvement :
   l'accueil affiche le voile pendant la création, la table reprend la même animation
   jusqu'à ce que tout soit prêt. */

export function ShufflingCards({ size = "sm" }: { size?: "sm" | "md" }) {
  const box = size === "md" ? "h-24 w-24" : "h-16 w-16";
  return (
    <div className={`relative ${box}`} aria-hidden>
      <motion.span
        className="absolute left-1 top-0"
        animate={{ rotate: [-14, 10, -14], y: [0, -6, 0] }}
        transition={{ repeat: Infinity, duration: 1.1, ease: "easeInOut" }}
      >
        <PlayingCard faceDown size={size} />
      </motion.span>
      <motion.span
        className={size === "md" ? "absolute left-9 top-1" : "absolute left-6 top-1"}
        animate={{ rotate: [12, -8, 12], y: [0, -10, 0] }}
        transition={{ repeat: Infinity, duration: 1.1, ease: "easeInOut", delay: 0.15 }}
      >
        <PlayingCard faceDown size={size} />
      </motion.span>
    </div>
  );
}

/* Écran d'attente plein cadre (connexion à une table, chargement des cartes). */
export function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center text-ivory-dim">
      <ShufflingCards />
      <p>{label}</p>
    </div>
  );
}

/* Voile de transition posé par-dessus l'écran courant, le temps d'une requête qui mène
   ailleurs (créer ou rejoindre une table) : le bouton a réagi, personne ne recliquera. */
export function TransitionOverlay({ label }: { label: string | null }) {
  return (
    <AnimatePresence>
      {label && (
        <motion.div
          key="overlay"
          role="status"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-felt-900/85 text-ivory-dim backdrop-blur-sm"
        >
          <ShufflingCards />
          <p className="font-semibold">{label}</p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
