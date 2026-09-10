/* Le catalogue des jeux. Ajouter un jeu = une entrée ici, un dossier src/games/<slug>/
   et ses routes src/app/<slug>/. Le slug est celui de la GameSpec côté serveur. */

export const APP_NAME = "Games";

export type GameMeta = {
  slug: string;
  name: string;
  tagline: string;
  players: string;
  /* Page d'accueil du jeu (créer / rejoindre une table). */
  path: string;
};

export const GAMES: GameMeta[] = [
  {
    slug: "nine-to-one",
    name: "Nine to One",
    tagline: "Pose plus fort ou ramasse tout. Le dernier avec des cartes perd.",
    players: "2 à 5 joueurs",
    path: "/nine-to-one",
  },
];

export function gameBySlug(slug: string): GameMeta | undefined {
  return GAMES.find((g) => g.slug === slug);
}

/* Route de la table d'un jeu. */
export function tablePath(game: string, code: string): string {
  return `/${game}/table/${code}`;
}
