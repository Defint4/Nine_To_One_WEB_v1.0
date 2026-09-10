import PlayingCard from "@/components/PlayingCard";

/* Le logo du Goulag : deux vies, un bouclier couché devant. */
export default function Wordmark() {
  return (
    <header className="mb-6 flex flex-col items-center">
      <div className="relative mb-2 h-16 w-24">
        <PlayingCard
          card={{ value: 13, suit: "spades" }}
          size="sm"
          className="absolute left-4 top-0 -rotate-6"
        />
        <PlayingCard
          card={{ value: 7, suit: "hearts" }}
          size="sm"
          className="absolute left-11 top-0 rotate-6"
        />
        <PlayingCard
          card={{ value: 3, suit: "clubs" }}
          size="sm"
          className="absolute left-7 top-6 rotate-90"
        />
      </div>
      <h1 className="text-2xl font-extrabold tracking-tight">Goulag</h1>
    </header>
  );
}
