import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Le badge dev de Next recouvre la barre du bas du jeu sur mobile et
  // intercepte les taps (dev uniquement) : on le coupe.
  devIndicators: false,
  // Test sur téléphone via le LAN : Next bloque sinon ses ressources dev
  // pour toute origine autre que localhost.
  allowedDevOrigins: ["192.168.1.105"],
};

export default nextConfig;
