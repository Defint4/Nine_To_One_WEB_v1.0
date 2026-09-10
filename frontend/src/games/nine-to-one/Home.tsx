"use client";

import GameHome from "@/components/GameHome";
import { GAME } from "./meta";
import Wordmark from "./Wordmark";

/* Accueil de Nine to One : l'accueil commun, avec le logo du jeu. */
export default function Home() {
  return <GameHome game={GAME} header={<Wordmark compact />} />;
}
