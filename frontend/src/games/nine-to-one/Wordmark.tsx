import PlayingCard from "@/components/PlayingCard";

export default function Wordmark({ compact }: { compact: boolean }) {
  // Les cartes md font 84 px de haut (w-14, ratio 2/3) : le conteneur doit les
  // absorber, rotation comprise, pour que l'as ne déborde pas sur le titre.
  return (
    <header className={`flex flex-col items-center ${compact ? "mb-6" : "mb-10"}`}>
      <div className={`relative ${compact ? "mb-2 h-16 w-20" : "mb-3 h-[6.2rem] w-28"}`}>
        <PlayingCard
          card={{ value: 9, suit: "spades" }}
          size={compact ? "sm" : "md"}
          className="absolute left-1 top-1 -rotate-12"
        />
        <PlayingCard
          card={{ value: 14, suit: "hearts" }}
          size={compact ? "sm" : "md"}
          className={`absolute rotate-12 ${compact ? "left-7 top-0" : "left-10 top-0"}`}
        />
      </div>
      <h1 className={`font-extrabold tracking-tight ${compact ? "text-2xl" : "text-4xl"}`}>
        Nine to One
      </h1>
      {!compact && <p className="mt-1 text-sm text-ivory-dim/80">La table est ouverte.</p>}
    </header>
  );
}
