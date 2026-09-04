/* Galerie d'avatars du jeu : un animal sur un jeton coloré.
   L'id ("renard-2") respecte le pattern serveur ^[a-z0-9-]{1,40}$. */

const ANIMALS: Record<string, string> = {
  renard: "🦊",
  panda: "🐼",
  grenouille: "🐸",
  chat: "🐱",
  lion: "🦁",
  pieuvre: "🐙",
  koala: "🐨",
  loup: "🐺",
  poussin: "🐤",
  tigre: "🐯",
  singe: "🐵",
  licorne: "🦄",
  requin: "🦈",
  hibou: "🦉",
  dino: "🦖",
  axolotl: "🦎",
};

const COINS = ["#c3402f", "#2f6bc3", "#c4923a", "#5b3fa8", "#2a8f6d", "#b8447e"];

export const AVATAR_IDS = Object.keys(ANIMALS).flatMap((animal) =>
  COINS.map((_, i) => `${animal}-${i}`)
);

/* Une sélection variée pour la galerie (un jeton par animal, couleurs tournantes). */
export const GALLERY = Object.keys(ANIMALS).map((animal, i) => `${animal}-${i % COINS.length}`);

export function avatarParts(id: string): { emoji: string; coin: string } {
  const [animal, index] = id.split("-");
  return {
    emoji: ANIMALS[animal] ?? "🃏",
    coin: COINS[Number(index)] ?? COINS[0],
  };
}
