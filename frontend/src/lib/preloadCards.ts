/* Préchargement des 52 faces : références retenues (pas de GC) + décodage anticipé,
   pour qu'aucune carte n'apparaisse blanche en pleine partie, même sur réseau lent.
   La promesse renvoyée se résout quand tout est chargé (une image en échec ne bloque
   pas : elle s'affichera en texte). */

const retained: HTMLImageElement[] = [];
let pending: Promise<void> | null = null;

export function preloadCards(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (pending) return pending;
  const loads: Promise<void>[] = [];
  for (let value = 2; value <= 14; value++) {
    for (const suit of ["hearts", "diamonds", "clubs", "spades"]) {
      const img = new Image();
      loads.push(
        new Promise<void>((resolve) => {
          img.onload = () => {
            img.decode?.().catch(() => {}).finally(resolve);
          };
          img.onerror = () => resolve();
        })
      );
      img.src = `/cards/${value}-${suit}.svg`;
      retained.push(img);
    }
  }
  pending = Promise.all(loads).then(() => undefined);
  return pending;
}
