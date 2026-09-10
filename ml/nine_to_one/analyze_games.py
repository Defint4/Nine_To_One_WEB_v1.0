"""Résumé des parties jouées contre les bots (backend/logs/games.jsonl).

Ne rejoue pas le moteur : tout se lit dans les événements publics de la manche.
Sert à voir où le bot punit l'humain (tas ramassés, coupes, blocages).

Usage : python analyze_games.py [chemin/games.jsonl] [--pseudo Matthieu]
"""

import argparse
import json
from collections import defaultdict


def summarize(record: dict) -> dict:
    seats = record["seats"]
    n = len(seats)
    ranks = record["ranks"]
    played = defaultdict(int)  # cartes posées
    moves = defaultdict(int)  # coups joués
    pickups = defaultdict(int)  # ramassages subis
    picked_cards = defaultdict(int)  # cartes ramassées
    cuts = defaultdict(int)  # coupes provoquées (10 ou carré)
    punishes = defaultdict(int)  # ramassages provoqués chez l'adversaire
    chases = defaultdict(int)  # enchaînements « bonne pioche »
    flips = defaultdict(int)  # cartes cachées retournées
    specials = defaultdict(lambda: defaultdict(int))  # 2 / 10 joués
    pile = 0  # taille courante du tas
    last_player = None

    for e in record["events"]:
        t = e["type"]
        if t == "cards_played":
            p = e["player"]
            moves[p] += 1
            played[p] += e["count"]
            pile += e["count"]
            last_player = p
            if e.get("chase"):
                chases[p] += 1
            if e["value"] in (2, 10):
                specials[p][e["value"]] += 1
        elif t == "card_flipped":
            flips[e["player"]] += 1
        elif t == "pile_picked_up":
            p = e["player"]
            pickups[p] += 1
            picked_cards[p] += pile
            if last_player is not None and last_player != p:
                punishes[last_player] += 1
            pile = 0
        elif t == "pile_cut":
            cuts[e["player"]] += 1
            pile = 0

    return {
        "at": record["at"],
        "code": record["code"],
        "n": n,
        "seats": seats,
        "ranks": ranks,
        "rows": [
            {
                "pseudo": s["pseudo"],
                "bot": s["bot"],
                "rank": ranks[i],
                "moves": moves[i],
                "played": played[i],
                "pickups": pickups[i],
                "picked_cards": picked_cards[i],
                "punishes": punishes[i],
                "cuts": cuts[i],
                "chases": chases[i],
                "flips": flips[i],
                "twos": specials[i][2],
                "tens": specials[i][10],
            }
            for i, s in enumerate(seats)
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(BACKEND / "logs" / "games.jsonl"))
    ap.add_argument("--pseudo", help="ne garder que les parties de ce joueur")
    ap.add_argument("--last", type=int, default=0, help="ne montrer que les N dernières")
    args = ap.parse_args()

    records = []
    with open(args.path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if args.pseudo and not any(s["pseudo"] == args.pseudo for s in r["seats"]):
                continue
            records.append(summarize(r))
    if args.last:
        records = records[-args.last :]
    if not records:
        print("aucune partie journalisée")
        return

    for r in records:
        print(f"\n{r['at']}  table {r['code']}  ({r['n']} joueurs)")
        print(
            f"  {'joueur':<18}{'':<11}{'rang':>5}{'coups':>7}{'cartes':>8}"
            f"{'ramass.':>9}{'reçues':>8}{'punit':>7}{'coupes':>8}{'chaîne':>8}{'2/10':>7}"
        )
        for row in sorted(r["rows"], key=lambda x: x["rank"] or 99):
            kind = f"bot {row['bot']}" if row["bot"] else "humain"
            print(
                f"  {row['pseudo']:<18}{kind:<11}{row['rank']:>5}{row['moves']:>7}{row['played']:>8}"
                f"{row['pickups']:>9}{row['picked_cards']:>8}{row['punishes']:>7}"
                f"{row['cuts']:>8}{row['chases']:>8}{str(row['twos']) + '/' + str(row['tens']):>7}"
            )

    # Bilan humain vs bots, par difficulté.
    tally = defaultdict(lambda: [0, 0])  # difficulté -> [victoires humaines, parties]
    stat = defaultdict(lambda: defaultdict(float))
    for r in records:
        humans = [row for row in r["rows"] if not row["bot"]]
        bots_rows = [row for row in r["rows"] if row["bot"]]
        if not humans or not bots_rows:
            continue
        diff = bots_rows[0]["bot"]
        tally[diff][1] += 1
        tally[diff][0] += int(humans[0]["rank"] == 1)
        for key in ("pickups", "picked_cards", "punishes", "cuts", "chases"):
            stat[diff]["h_" + key] += humans[0][key]
            stat[diff]["b_" + key] += sum(b[key] for b in bots_rows) / len(bots_rows)

    print("\nBilan")
    for diff, (wins, total) in sorted(tally.items()):
        s = stat[diff]
        print(
            f"  vs {diff:<8} {wins}/{total} victoires humaines · ramassages {s['h_pickups'] / total:.1f} "
            f"contre {s['b_pickups'] / total:.1f} · cartes ramassées {s['h_picked_cards'] / total:.0f} "
            f"contre {s['b_picked_cards'] / total:.0f} · coupes {s['h_cuts'] / total:.1f} "
            f"contre {s['b_cuts'] / total:.1f}"
        )


if __name__ == "__main__":
    main()
