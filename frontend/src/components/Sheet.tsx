"use client";

import { motion } from "motion/react";

export function Sheet({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <motion.div
        initial={{ y: 60, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        onClick={(e) => e.stopPropagation()}
        className="relative z-10 w-full max-w-md rounded-t-3xl bg-felt-800 p-5 pb-8 ring-1 ring-white/15"
      >
        {children}
      </motion.div>
    </div>
  );
}
