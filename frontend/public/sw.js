/* Service worker minimal : requis pour l'installation PWA.
   Le jeu est temps réel, on ne met rien en cache — le réseau fait foi. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {
  /* passthrough réseau */
});
