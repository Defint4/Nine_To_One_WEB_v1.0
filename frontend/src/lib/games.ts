/* Le catalogue des jeux. Ajouter un jeu = une entrée ici, un dossier src/games/<slug>/
   et ses routes src/app/<slug>/. Le slug est celui de la GameSpec côté serveur. */

export const APP_NAME = "Games";

/* La page de sélection, où l'on arrive une fois identifié. */
export const HUB_PATH = "/games";

export type GameMeta = {
  slug: string;
  name: string;
  tagline: string;
  players: string;
  /* Page d'accueil du jeu (créer / rejoindre une table). */
  path: string;
  /* Le « tapis » du jeu sur la page de sélection : chaque jeu a sa matière. */
  mat: string;
  /* Faux tant que le jeu n'est pas jouable : sa tuile est visible mais inerte. */
  available: boolean;
};

export const GAMES: GameMeta[] = [
  {
    slug: "nine-to-one",
    name: "Nine to One",
    tagline: "Pose plus fort ou ramasse tout. Le dernier avec des cartes perd.",
    players: "2 à 5 joueurs",
    path: "/nine-to-one",
    mat: "radial-gradient(130% 110% at 85% 15%, #2a7a62 0%, #1b5443 45%, #0f3529 100%)",
    available: true,
  },
  {
    slug: "goulag",
    name: "Goulag",
    tagline: "Deux cartes de vie, une de défense. Attaque, charge ou blinde-toi.",
    players: "2 à 6 joueurs",
    path: "/goulag",
    mat: "radial-gradient(130% 110% at 85% 15%, #4a5a6c 0%, #2b3644 45%, #171e28 100%)",
    available: true,
  },
];

export function gameBySlug(slug: string): GameMeta | undefined {
  return GAMES.find((g) => g.slug === slug);
}

/* Route de la table d'un jeu. */
export function tablePath(game: string, code: string): string {
  return `/${game}/table/${code}`;
}
