/* Sons du jeu : vrais bruits de cartes (pack casino de Kenney, CC0, /public/sounds),
   plus un petit carillon synthétisé pour signaler ton tour. */

const KEY = "games:muted";
let ctx: AudioContext | null = null;
const raw = new Map<string, ArrayBuffer>();
const buffers = new Map<string, AudioBuffer>();

const FILES = ["place-1", "place-2", "place-3", "slide-1", "slide-2", "shove-1", "fan"];

export function isMuted(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setMuted(muted: boolean) {
  try {
    localStorage.setItem(KEY, muted ? "1" : "0");
  } catch {
    /* stockage indisponible */
  }
}

/* À appeler en entrant sur une table : télécharge les échantillons en avance. */
export function preloadSounds() {
  for (const name of FILES) {
    if (raw.has(name)) continue;
    fetch(`/sounds/${name}.wav`)
      .then((res) => res.arrayBuffer())
      .then((buf) => raw.set(name, buf))
      .catch(() => {
        /* le jeu reste silencieux pour ce son */
      });
  }
}

function audio(): AudioContext | null {
  if (typeof window === "undefined" || isMuted()) return null;
  try {
    ctx ??= new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

async function sample(names: string[], volume: number) {
  const ac = audio();
  if (!ac) return;
  const name = names[Math.floor(Math.random() * names.length)];
  try {
    let buffer = buffers.get(name);
    if (!buffer) {
      const data = raw.get(name);
      if (!data) return;
      buffer = await ac.decodeAudioData(data.slice(0));
      buffers.set(name, buffer);
    }
    const src = ac.createBufferSource();
    src.buffer = buffer;
    const gain = ac.createGain();
    gain.gain.value = volume;
    src.connect(gain).connect(ac.destination);
    src.start();
  } catch {
    /* décodage impossible : silence */
  }
}

function tone(freq: number, at: number, dur: number, volume: number) {
  const ac = audio();
  if (!ac) return;
  const osc = ac.createOscillator();
  osc.type = "sine";
  osc.frequency.value = freq;
  const gain = ac.createGain();
  const t = ac.currentTime + at;
  gain.gain.setValueAtTime(0, t);
  gain.gain.linearRampToValueAtTime(volume, t + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(gain).connect(ac.destination);
  osc.start(t);
  osc.stop(t + dur + 0.05);
}

export const sfx = {
  play: () => sample(["place-1", "place-2", "place-3"], 0.8),
  flip: () => sample(["slide-2"], 0.7),
  deal: () => sample(["fan"], 0.7),
  cut: () => sample(["shove-1"], 0.9),
  pickup: () => sample(["slide-1"], 0.8),
  yourTurn: () => {
    tone(660, 0, 0.12, 0.1);
    tone(880, 0.1, 0.18, 0.1);
  },
  /* Coup interdit : un petit "non" sourd. */
  nope: () => {
    tone(160, 0, 0.09, 0.14);
    tone(120, 0.08, 0.12, 0.12);
  },
  /* Arpège montant pour le vainqueur, descente pour le perdant. */
  win: () => {
    [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.13, 0.35, 0.11));
  },
  lose: () => {
    [392, 330, 262, 196].forEach((f, i) => tone(f, i * 0.16, 0.4, 0.1));
  },
  /* Petit "pop" à la réception d'un message. */
  pop: () => tone(980, 0, 0.07, 0.07),
};

export function vibrate(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* non supporté */
  }
}
