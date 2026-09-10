"use client";

import { motion } from "motion/react";
import PlayingCard from "@/components/PlayingCard";
import type { CardT } from "@/lib/types";

/* Une carte qui se retourne en vrai 3D : dos puis face, autour de son axe vertical.
   Utilisée dans les vols (révélation d'une carte piochée) et au centre de la table. */
export default function FlipCard({
  card,
  size = "md",
  delay = 0,
  duration = 0.5,
}: {
  card: CardT;
  size?: "sm" | "ms" | "md" | "lg";
  delay?: number;
  duration?: number;
}) {
  return (
    <span className="block [perspective:600px]">
      <motion.span
        className="relative block [transform-style:preserve-3d]"
        initial={{ rotateY: 180 }}
        animate={{ rotateY: 0 }}
        transition={{ delay, duration, ease: [0.4, 0, 0.2, 1] }}
      >
        <span className="block [backface-visibility:hidden]">
          <PlayingCard card={card} size={size} />
        </span>
        <span
          className="absolute inset-0 block [backface-visibility:hidden]"
          style={{ transform: "rotateY(180deg)" }}
        >
          <PlayingCard faceDown size={size} />
        </span>
      </motion.span>
    </span>
  );
}
