"use client";

/* Couche d'effets : particules (étincelles, braises, poussière), traînées de tir et
   ondes de choc dessinées sur un canvas plein écran, plus des voiles d'écran (éclair
   d'impact, vignette de mort, lueur dorée). Sœur de FlightLayer : on lui parle par des
   fonctions globales, positionnées sur les ancres de la table. Le canvas ne tourne que
   tant qu'il y a quelque chose à dessiner. */

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { anchorCenter } from "@/lib/anchors";

type Point = { x: number; y: number };

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number; // secondes restantes
  total: number;
  size: number;
  color: string;
  gravity: number;
  drag: number;
  streak: boolean; // dessinée comme un trait dans le sens de la vitesse
};

type Ring = { x: number; y: number; life: number; total: number; radius: number; color: string; width: number };

type Tracer = {
  from: Point;
  to: Point;
  life: number;
  total: number;
  color: string;
  width: number;
};

type Screen = { id: number; kind: "hit" | "gold" | "dark" };

const particles: Particle[] = [];
const rings: Ring[] = [];
const tracers: Tracer[] = [];
let raf = 0;
let canvas: HTMLCanvasElement | null = null;
let setScreenFn: ((s: Screen | null) => void) | null = null;
let screenId = 0;
let last = 0;

function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function resolve(at: string | Point): Point | null {
  return typeof at === "string" ? anchorCenter(at) : at;
}

/* Une gerbe de particules depuis un point. `spread` : angle d'ouverture (rad) autour
   de `angle` ; sans angle, dans toutes les directions. */
export function burst(
  at: string | Point,
  options: {
    colors: string[];
    count?: number;
    speed?: number;
    angle?: number;
    spread?: number;
    size?: number;
    life?: number;
    gravity?: number;
    streak?: boolean;
  },
) {
  const p = resolve(at);
  if (!p || reducedMotion()) return;
  const count = options.count ?? 24;
  const speed = options.speed ?? 320;
  const spread = options.spread ?? Math.PI * 2;
  const base = options.angle ?? 0;
  for (let i = 0; i < count; i++) {
    const a = base + (Math.random() - 0.5) * spread;
    const v = speed * (0.35 + Math.random() * 0.85);
    const life = (options.life ?? 0.7) * (0.6 + Math.random() * 0.6);
    particles.push({
      x: p.x,
      y: p.y,
      vx: Math.cos(a) * v,
      vy: Math.sin(a) * v,
      life,
      total: life,
      size: (options.size ?? 3) * (0.6 + Math.random() * 0.8),
      color: options.colors[Math.floor(Math.random() * options.colors.length)],
      gravity: options.gravity ?? 900,
      drag: 2.2,
      streak: options.streak ?? true,
    });
  }
  start();
}

/* Onde de choc : un cercle qui s'élargit et s'efface. */
export function shockwave(
  at: string | Point,
  options: { color?: string; radius?: number; duration?: number; width?: number } = {},
) {
  const p = resolve(at);
  if (!p || reducedMotion()) return;
  rings.push({
    x: p.x,
    y: p.y,
    life: options.duration ?? 0.45,
    total: options.duration ?? 0.45,
    radius: options.radius ?? 90,
    color: options.color ?? "rgba(255,255,255,0.9)",
    width: options.width ?? 3,
  });
  start();
}

/* Traînée de tir : un trait lumineux qui file d'un point à l'autre. */
export function tracer(
  from: string | Point,
  to: string | Point,
  options: { color?: string; duration?: number; width?: number } = {},
) {
  const a = resolve(from);
  const b = resolve(to);
  if (!a || !b || reducedMotion()) return;
  tracers.push({
    from: a,
    to: b,
    life: options.duration ?? 0.35,
    total: options.duration ?? 0.35,
    color: options.color ?? "rgba(255,220,140,0.95)",
    width: options.width ?? 3,
  });
  start();
}

/* Voile d'écran : éclair blanc-rouge d'impact, lueur dorée, ou assombrissement. */
export function screenFx(kind: Screen["kind"]) {
  setScreenFn?.({ id: ++screenId, kind });
}

function start() {
  if (raf || !canvas) return;
  last = performance.now();
  raf = requestAnimationFrame(frame);
}

function frame(now: number) {
  raf = 0;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);

  for (let i = tracers.length - 1; i >= 0; i--) {
    const t = tracers[i];
    t.life -= dt;
    if (t.life <= 0) {
      tracers.splice(i, 1);
      continue;
    }
    // La tête avance de 0 à 1, la queue suit avec un retard : un trait qui file.
    const head = Math.min(1, (1 - t.life / t.total) * 1.35);
    const tail = Math.max(0, head - 0.4);
    const hx = t.from.x + (t.to.x - t.from.x) * head;
    const hy = t.from.y + (t.to.y - t.from.y) * head;
    const tx = t.from.x + (t.to.x - t.from.x) * tail;
    const ty = t.from.y + (t.to.y - t.from.y) * tail;
    const grad = ctx.createLinearGradient(tx, ty, hx, hy);
    grad.addColorStop(0, "rgba(255,255,255,0)");
    grad.addColorStop(1, t.color);
    ctx.strokeStyle = grad;
    ctx.lineWidth = t.width;
    ctx.lineCap = "round";
    ctx.shadowColor = t.color;
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(hx, hy);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  for (let i = rings.length - 1; i >= 0; i--) {
    const r = rings[i];
    r.life -= dt;
    if (r.life <= 0) {
      rings.splice(i, 1);
      continue;
    }
    const k = 1 - r.life / r.total;
    const ease = 1 - Math.pow(1 - k, 3);
    ctx.globalAlpha = (1 - k) * 0.9;
    ctx.strokeStyle = r.color;
    ctx.lineWidth = r.width * (1 - k) + 0.5;
    ctx.beginPath();
    ctx.arc(r.x, r.y, 6 + r.radius * ease, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.life -= dt;
    if (p.life <= 0) {
      particles.splice(i, 1);
      continue;
    }
    p.vy += p.gravity * dt;
    p.vx -= p.vx * p.drag * dt;
    p.vy -= p.vy * p.drag * dt;
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    const k = p.life / p.total;
    ctx.globalAlpha = Math.min(1, k * 1.6);
    ctx.fillStyle = p.color;
    ctx.strokeStyle = p.color;
    if (p.streak) {
      const len = Math.min(18, Math.hypot(p.vx, p.vy) * 0.03);
      const n = Math.hypot(p.vx, p.vy) || 1;
      ctx.lineWidth = p.size * k + 0.4;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(p.x - (p.vx / n) * len, p.y - (p.vy / n) * len);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * (0.4 + k * 0.6), 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;

  if (particles.length || rings.length || tracers.length) {
    raf = requestAnimationFrame(frame);
  }
}

export default function FxLayer() {
  const [screen, setScreen] = useState<Screen | null>(null);

  useEffect(() => {
    setScreenFn = setScreen;
    const el = canvas;
    const resize = () => {
      if (!el) return;
      const dpr = window.devicePixelRatio || 1;
      el.width = Math.round(window.innerWidth * dpr);
      el.height = Math.round(window.innerHeight * dpr);
    };
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      setScreenFn = null;
    };
  }, []);

  useEffect(() => {
    if (!screen) return;
    const t = setTimeout(() => setScreen(null), screen.kind === "dark" ? 900 : 260);
    return () => clearTimeout(t);
  }, [screen]);

  const veil = {
    hit: {
      className: "bg-[radial-gradient(circle_at_50%_45%,rgba(255,235,210,0.55),rgba(195,64,47,0.25)_60%,transparent)]",
      duration: 0.26,
    },
    gold: {
      className: "bg-[radial-gradient(circle_at_50%_60%,rgba(229,181,74,0.45),transparent_65%)]",
      duration: 0.5,
    },
    dark: {
      className: "bg-[radial-gradient(circle_at_50%_50%,transparent_35%,rgba(0,0,0,0.75))]",
      duration: 0.9,
    },
  };

  return (
    <>
      <canvas
        ref={(el) => {
          canvas = el;
        }}
        aria-hidden
        className="pointer-events-none fixed inset-0 z-[29] h-full w-full"
      />
      <AnimatePresence>
        {screen && (
          <motion.div
            key={screen.id}
            aria-hidden
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: veil[screen.kind].duration, times: [0, 0.2, 1] }}
            className={`pointer-events-none fixed inset-0 z-[31] ${veil[screen.kind].className}`}
          />
        )}
      </AnimatePresence>
    </>
  );
}
