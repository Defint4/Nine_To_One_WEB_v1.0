import Leaderboard from "@/components/Leaderboard";
import { GAME } from "@/games/nine-to-one/meta";

export default function Page() {
  return <Leaderboard game={GAME} />;
}
