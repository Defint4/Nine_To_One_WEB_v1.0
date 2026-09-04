import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nine to One",
    short_name: "Nine to One",
    description: "Le jeu de cartes à jouer entre amis.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0c2c22",
    theme_color: "#0c2c22",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
