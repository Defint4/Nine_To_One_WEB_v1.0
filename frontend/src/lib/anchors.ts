/* Registre d'ancres : des points de la table (pioche, tas, avatars…) que les
   animations de vol de cartes utilisent comme origine ou destination. */

const anchors = new Map<string, HTMLElement>();

export function registerAnchor(key: string) {
  return (el: HTMLElement | null) => {
    if (el) anchors.set(key, el);
    else anchors.delete(key);
  };
}

export function anchorCenter(key: string): { x: number; y: number } | null {
  const el = anchors.get(key);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

/* Décalage à appliquer à `el` pour qu'il paraisse partir de l'ancre. */
export function offsetFromAnchor(key: string, el: HTMLElement): { x: number; y: number } | null {
  const from = anchorCenter(key);
  if (!from) return null;
  const rect = el.getBoundingClientRect();
  return { x: from.x - (rect.left + rect.width / 2), y: from.y - (rect.top + rect.height / 2) };
}

/* Vecteur entre deux ancres (pour des sorties de tas approchées). */
export function anchorDelta(fromKey: string, toKey: string): { x: number; y: number } | null {
  const from = anchorCenter(fromKey);
  const to = anchorCenter(toKey);
  if (!from || !to) return null;
  return { x: to.x - from.x, y: to.y - from.y };
}
