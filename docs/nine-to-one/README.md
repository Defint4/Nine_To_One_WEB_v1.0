# Nine to One

Jeu de cartes multijoueur (2 à 5 joueurs) : on pose une carte égale ou plus forte que la
précédente, on repioche à 3 tant que la pioche dure, bloqué on ramasse tout le tas. Main
vidée, on joue ses cartes visibles puis ses cachées à l'aveugle. Le dernier avec des
cartes perd. Règles complètes : [regles-officielles.txt](regles-officielles.txt) ;
arbitrages des zones floues dans le docstring de `backend/app/games/nine_to_one/engine/game.py`.

Slug : `nine-to-one` · Production : https://games.matthieuguiot.dev/nine-to-one

## Où est le code

```
backend/app/games/nine_to_one/
  engine/        règles pures (aucune I/O) : cards, state, game
  spec.py        GameSpec : traduit les messages WebSocket en appels au moteur
  views.py       ce que chaque siège a le droit de voir
  bots.py        Facile / Normal / Difficile, cadencement
  botbrain.py    réseau numpy + recherche (miroir de ml/nine_to_one/rl_env2.py et search.py)
  *.npz          poids du bot Difficile (acteur + critique), versionnés
  tests/         68 tests du moteur
frontend/src/games/nine-to-one/
  Home.tsx       créer / rejoindre une table, tables ouvertes
  TablePage.tsx  lobby (échange initial, bots, timer) + table + paramètres
  GameTable.tsx  la table de jeu animée
  socket.ts      useNineToOneSocket : actions du jeu au-dessus du socket commun
  types.ts       RoomView / PlayerView du jeu
frontend/src/app/nine-to-one/     routes : /nine-to-one, /nine-to-one/table/[code]
ml/nine_to_one/                   entraînement et évaluation des bots (torch, hors production)
```

## Actions WebSocket du jeu

Envoyées par le client sur le socket de table (`{"action": ..., ...}`), en plus des actions
communes de la plateforme (chat, emote, config, add_bot, remove_bot, rematch, leave, sync) :

| action | champs | phase |
|---|---|---|
| `swap` | `hand_index`, `face_up_index` | lobby, avant « prêt » |
| `ready` | `ready` (bool) | lobby |
| `play` | `value`, `count`, `direction` (`>=` / `<=` pour un 7) | partie |
| `flip` | `index` | partie, main vide |
| `chase` | `count` | « bonne pioche » |
| `chase_flip` | `index` | « bonne pioche », main vide |

## Les bots

Trois niveaux, ajoutés par le créateur de la table depuis le lobby :

| Niveau | Politique | Coût serveur |
|---|---|---|
| Facile | coup légal au hasard, une carte à la fois, n'enchaîne jamais | nul |
| Normal | heuristique « économe » : plus petite carte normale, multiples, garde ses 2 et 10, enchaîne | nul |
| Difficile | réseau (MLP 223→512→512→256, numpy) + recherche sur les cartes cachées | 1 cœur pendant `BOT_TIME_BUDGET` s par coup |

Le bot Difficile lit uniquement ce qu'un joueur verrait à sa place (sa vue + les
événements publics) : il ne triche pas. Il réfléchit dans un thread séparé (au plus
`BOT_THREADS` réflexions à la fois, chacune bornée à `BOT_TIME_BUDGET` secondes), la boucle
réseau continue de servir les autres tables pendant ce temps. Mémoire : ~75 Mo pour le
processus backend, poids compris. Aucune dépendance torch en production.

Chaque manche jouée contre un bot est journalisée dans `backend/logs/games.jsonl`
(`GAMES_LOG_PATH`, vide pour désactiver). Bilan : `python3 ml/nine_to_one/analyze_games.py`.

Les bots ne comptent pas dans les statistiques des joueurs, suivent la revanche et se
mettent prêts tout seuls.

## Entraîner les bots (hors production)

Nécessite un venv avec torch (voir `ml/nine_to_one/train_v2.py`). Depuis la racine du repo :

```bash
python ml/nine_to_one/train_v2.py --minutes 360 --workers 5 --envs 48 --out v2      # PPO en ligue, 2-5 joueurs
python ml/nine_to_one/export_policy2.py v2.best.pt backend/app/games/nine_to_one/bot_policy_v2.npz
backend/.venv/bin/python ml/nine_to_one/check_obs_parity2.py                        # serveur == entraînement
python ml/nine_to_one/ladder.py backend/app/games/nine_to_one/bot_policy_v2.npz \
       backend/app/games/nine_to_one/bot_policy_v2_critic.npz                       # Elo
```

La politique jouée par le serveur est celle de `botbrain.py` ; `ml/nine_to_one/search.py`
et `ladder.py` l'évaluent hors ligne avec ce même code.

## Test de charge

```bash
python ml/nine_to_one/loadtest.py --api https://games.matthieuguiot.dev --tables 5 --bots 3
```
