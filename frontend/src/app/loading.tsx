import { LoadingScreen } from "@/components/Loading";

/* Entre deux pages, le temps que la suivante arrive : le même battage de cartes
   que partout ailleurs, jamais un écran vide. */
export default function Loading() {
  return <LoadingScreen label="Un instant…" />;
}
