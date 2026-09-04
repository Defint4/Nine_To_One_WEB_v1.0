"use client";

/* Couche de "vols" : des éléments éphémères (dos de carte, emoji…) qui traversent
   l'écran d'une ancre à une autre — pioche → adversaire, avatar → avatar… */

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { anchorCenter } from "@/lib/anchors";

type Flight = {
  id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  content: React.ReactNode;
  delay: number;
  duration: number;
  still: boolean;
};

let nextId = 0;
let spawnFn: ((f: Omit<Flight, "id">) => void) | null = null;

export function spawnFlight(options: {
  from: string;
  to: string;
  content: React.ReactNode;
  delay?: number;
  duration?: number;
  /* Vol "posé" : l'élément apparaît à l'ancre et y reste (carte qui repose sur le tas). */
  still?: boolean;
}) {
  const from = anchorCenter(options.from);
  const to = anchorCenter(options.to);
  if (!from || !to || !spawnFn) return;
  spawnFn({
    x1: from.x,
    y1: from.y,
    x2: to.x,
    y2: to.y,
    content: options.content,
    delay: options.delay ?? 0,
    duration: options.duration ?? 0.45,
    still: options.still ?? false,
  });
}

export default function FlightLayer() {
  const [flights, setFlights] = useState<Flight[]>([]);

  useEffect(() => {
    spawnFn = (f) => {
      const id = ++nextId;
      setFlights((prev) => [...prev, { ...f, id }]);
      setTimeout(
        () => setFlights((prev) => prev.filter((x) => x.id !== id)),
        (f.delay + f.duration) * 1000 + (f.still ? 20 : 200)
      );
    };
    return () => {
      spawnFn = null;
    };
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 z-30">
      <AnimatePresence>
        {flights.map((f) => (
          <motion.span
            key={f.id}
            initial={{ x: f.x1, y: f.y1, opacity: 0, scale: f.still ? 1 : 0.6 }}
            animate={{
              x: f.x2,
              y: f.y2,
              opacity: [0, 1, 1],
              scale: f.still ? 1 : [0.6, 1, 0.9],
            }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            transition={{ duration: f.duration, delay: f.delay, ease: [0.3, 0.7, 0.4, 1] }}
            className="absolute left-0 top-0 -translate-x-1/2 -translate-y-1/2"
          >
            <span className="block -translate-x-1/2 -translate-y-1/2">{f.content}</span>
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  );
}
