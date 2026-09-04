/* Préchargement des 52 faces : références retenues (pas de GC) + décodage anticipé,
   pour qu'aucune carte n'apparaisse blanche en pleine partie, même sur réseau lent. */

const retained: HTMLImageElement[] = [];

export function preloadCards() {
  if (typeof window === "undefined" || retained.length) return;
  for (let value = 2; value <= 14; value++) {
    for (const suit of ["hearts", "diamonds", "clubs", "spades"]) {
      const img = new Image();
      img.src = `/cards/${value}-${suit}.svg`;
      img.decode?.().catch(() => {
        /* décodage au moment de l'affichage, au pire */
      });
      retained.push(img);
    }
  }
}
