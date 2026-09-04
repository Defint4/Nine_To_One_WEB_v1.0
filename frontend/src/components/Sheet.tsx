"use client";

import { motion } from "motion/react";
import { useEffect, useRef } from "react";

/* Bottom-sheet. Sur iOS, le clavier ne réduit pas la fenêtre de mise en page : un
   élément fixé en bas reste derrière lui et Safari fait défiler toute la page pour
   montrer le champ (l'app paraît ensuite « remontée », avec une bande vide en bas).
   On suit donc le viewport visuel : la feuille se cale au-dessus du clavier, et on
   remet la page en place quand elle se ferme. */
export function Sheet({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const vv = window.visualViewport;
    const el = ref.current;
    if (!vv || !el) return;
    const fit = () => {
      el.style.top = `${vv.offsetTop}px`;
      el.style.height = `${vv.height}px`;
    };
    fit();
    vv.addEventListener("resize", fit);
    vv.addEventListener("scroll", fit);
    return () => {
      vv.removeEventListener("resize", fit);
      vv.removeEventListener("scroll", fit);
      window.scrollTo(0, 0);
    };
  }, []);

  return (
    <div
      ref={ref}
      className="fixed inset-x-0 top-0 z-40 flex h-full items-end justify-center"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/40" />
      <motion.div
        initial={{ y: 60, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        onClick={(e) => e.stopPropagation()}
        className="relative z-10 max-h-full w-full max-w-md overflow-y-auto rounded-t-3xl bg-felt-800 p-5 pb-[max(2rem,env(safe-area-inset-bottom))] ring-1 ring-white/15"
      >
        {children}
      </motion.div>
    </div>
  );
}
