import Leaderboard from "@/components/Leaderboard";
import { GAME } from "@/games/goulag/meta";

export default function Page() {
  return <Leaderboard game={GAME} />;
}
