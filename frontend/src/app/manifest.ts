import type { MetadataRoute } from "next";
import { APP_NAME } from "@/lib/games";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: APP_NAME,
    short_name: APP_NAME,
    description: "Des jeux entre amis, sur le téléphone.",
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
