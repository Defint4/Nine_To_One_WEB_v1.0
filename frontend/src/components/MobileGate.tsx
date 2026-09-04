"use client";

import { useEffect, useState } from "react";

/* Sur téléphone, le jeu se joue dans l'app installée (PWA), pas dans le navigateur.
   Ce composant bloque le navigateur mobile et guide l'installation.
   Sur ordinateur, le navigateur reste libre. */

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

type GateState = "checking" | "open" | "install";

export default function MobileGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [ios, setIos] = useState(false);
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* l'installation restera possible via le manifest seul */
      });
    }

    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      ("standalone" in navigator && (navigator as { standalone?: boolean }).standalone === true);
    const mobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    const gated = mobile && !standalone && process.env.NODE_ENV === "production";

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIos(/iPhone|iPad|iPod/i.test(navigator.userAgent));
    setState(gated ? "install" : "open");

    const onPrompt = (e: Event) => {
      e.preventDefault();
      setInstallEvent(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (state === "open") return <>{children}</>;
  if (state === "checking") return null;

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col items-center justify-center gap-6 px-6 text-center">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon-192.png" alt="" className="size-24 rounded-3xl shadow-card" />
      <div>
        <h1 className="text-3xl font-extrabold">Nine to One</h1>
        <p className="mt-2 text-ivory-dim/90">
          Le jeu se joue dans l&rsquo;application, pas dans le navigateur. Installe-la sur ton
          écran d&rsquo;accueil, c&rsquo;est fait en dix secondes.
        </p>
      </div>

      {installed ? (
        <p className="rounded-2xl bg-gold/15 px-4 py-3 font-bold text-gold ring-1 ring-gold/40">
          C&rsquo;est installé ! Ouvre Nine to One depuis ton écran d&rsquo;accueil.
        </p>
      ) : ios ? (
        <ol className="flex flex-col gap-3 text-left">
          <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
            <span className="text-2xl">1️⃣</span> Touche le bouton Partager
            <ShareIcon />
          </li>
          <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
            <span className="text-2xl">2️⃣</span> Choisis « Sur l&rsquo;écran d&rsquo;accueil »
          </li>
          <li className="flex items-center gap-3 rounded-2xl bg-black/25 p-3 ring-1 ring-white/10">
            <span className="text-2xl">3️⃣</span> Lance le jeu depuis la nouvelle icône
          </li>
        </ol>
      ) : installEvent ? (
        <button
          type="button"
          onClick={() => installEvent.prompt()}
          className="rounded-2xl bg-gold px-8 py-4 text-lg font-extrabold text-ink shadow-card active:translate-y-0.5"
        >
          Installer l&rsquo;application
        </button>
      ) : (
        <p className="rounded-2xl bg-black/25 p-4 text-left ring-1 ring-white/10">
          Dans le menu du navigateur (⋮), choisis « Ajouter à l&rsquo;écran d&rsquo;accueil »,
          puis lance le jeu depuis la nouvelle icône.
        </p>
      )}
    </main>
  );
}

function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-6 shrink-0 fill-none stroke-gold stroke-2">
      <path d="M12 3v12M8 7l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 11v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8" strokeLinecap="round" />
    </svg>
  );
}
