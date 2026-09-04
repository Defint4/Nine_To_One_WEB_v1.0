/* Identités mémorisées sur l'appareil : un joueur revient et reprend son pseudo en un tap.
   Le token signé prouve juste "ce pseudo sur cet appareil" — pas de compte, pas de mot de passe. */

export type StoredProfile = {
  pseudo: string;
  avatar: string;
  token: string;
  lastUsed: number;
};

const KEY = "ninetoone:profiles";
const CURRENT_KEY = "ninetoone:current";

function read(): StoredProfile[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as StoredProfile[]) : [];
  } catch {
    return [];
  }
}

function write(profiles: StoredProfile[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(profiles));
  } catch {
    /* stockage indisponible : l'app reste utilisable, sans mémoire */
  }
}

export function listProfiles(): StoredProfile[] {
  return read().sort((a, b) => b.lastUsed - a.lastUsed);
}

export function saveProfile(profile: Omit<StoredProfile, "lastUsed">) {
  const others = read().filter((p) => p.pseudo.toLowerCase() !== profile.pseudo.toLowerCase());
  write([{ ...profile, lastUsed: Date.now() }, ...others]);
  try {
    localStorage.setItem(CURRENT_KEY, profile.pseudo.toLowerCase());
  } catch {
    /* idem */
  }
}

export function forgetProfile(pseudo: string) {
  write(read().filter((p) => p.pseudo.toLowerCase() !== pseudo.toLowerCase()));
}

export function currentProfile(): StoredProfile | null {
  try {
    const key = localStorage.getItem(CURRENT_KEY);
    if (!key) return null;
    return read().find((p) => p.pseudo.toLowerCase() === key) ?? null;
  } catch {
    return null;
  }
}

const TABLE_KEY = "ninetoone:last-table";

/* Dernière table visitée : permet de proposer « Reprendre la partie » à l'accueil. */
export function rememberTable(code: string) {
  try {
    localStorage.setItem(TABLE_KEY, code);
  } catch {
    /* idem */
  }
}

export function lastTable(): string | null {
  try {
    return localStorage.getItem(TABLE_KEY);
  } catch {
    return null;
  }
}

export function forgetTable() {
  try {
    localStorage.removeItem(TABLE_KEY);
  } catch {
    /* idem */
  }
}

export function signOut() {
  try {
    localStorage.removeItem(CURRENT_KEY);
  } catch {
    /* idem */
  }
}
