# Goulag

Jeu de cartes de combat (2 à 6 joueurs) : deux cartes de vie, une de défense, et à
chaque tour un choix à l'aveugle avant de piocher. Le dernier survivant gagne.

Slug : `goulag` · Production : https://games.matthieuguiot.dev/goulag

## Règles

Un seul paquet de 52 cartes. Une carte vaut sa valeur : As = 1, Valet = 11, Dame = 12,
Roi = 13.

**Mise en place.** Chacun reçoit 3 cartes. Les deux plus fortes sont ses vies (leur somme),
posées face visible ; la plus faible est sa défense, posée devant. Commence celui qui a
la plus petite défense, puis le moins de vies en cas d'égalité, puis le sort. On joue
ensuite dans le sens horaire.

**Le tour.** Le joueur annonce ce qu'il fait *avant* de voir la carte du dessus de la pioche :

- Défense : la carte piochée remplace la défense d'un joueur de son choix, lui-même ou un
  autre (une carte faible imposée à un adversaire l'affaiblit). L'ancienne va à la défausse.
- Charge : la carte est posée face cachée à côté de ses vies, sans être vue. Deux charges
  maximum.
- Attaque : la carte piochée, plus toutes ses charges, frappe un adversaire. Les dégâts
  sont attaque moins défense de la cible ; si rien ne dépasse, rien ne passe. La défense
  n'est jamais consommée. Toutes les cartes jouées vont à la défausse.

Pour la défense et l'attaque, la cible est désignée elle aussi à l'aveugle : la carte
n'est piochée et révélée qu'une fois la cible choisie.

**Charges.** Elles restent en place tant qu'on ne les utilise pas. Un joueur touché aux
vies perd les siennes.

**Vies après dégâts.** On recompose les cartes pour afficher le nouveau total : la plus
forte reste, l'autre est remplacée par la carte exacte du complément, cherchée d'abord
dans la défausse puis dans la pioche. Si le total descend sous la plus forte, une seule
carte de la valeur exacte. Exemple : 6 + 4 = 10, trois dégâts → 6 + As.

**Pioche.** Elle ne se régénère qu'au moment où sa dernière carte est prise : la défausse
est alors mélangée et devient la pioche.

**Mort.** À zéro, les vies partent à la défausse et le mort choisit une couleur. On
retourne la carte du dessus : bonne couleur, il revit avec cette carte pour seule vie (sa
défense reste). Sinon, seconde et dernière chance avec la même couleur : on coupe la pioche
et on retourne la carte du milieu. Bonne couleur, il revit avec ; sinon il est éliminé et sa défense rejoint la défausse.
Le jeu continue sans lui, le tour passe au voisin de l'attaquant.

**Œil de faucon.** Un joueur dont la vie n'est plus qu'un As seul voit la carte du dessus
avant d'annoncer son action.

## Arbitrages retenus

- Annonce puis cible, le tout à l'aveugle ; la carte est piochée et révélée ensuite (seul
  l'œil de faucon la connaît d'avance).
- Une attaque qui touche les vies fait perdre ses charges au défenseur ; la défense et les
  charges d'un joueur éliminé vont à la défausse (elles reviennent en jeu).
- S'il n'existe aucune carte de la valeur exacte à recomposer, deux cartes qui font la
  somme ; s'il n'existe aucune combinaison (les quatre As déjà en jeu alors qu'il faut 1),
  la plus petite carte au-dessus, au bénéfice du blessé (événement `lives_rounded_up`).
- Les cartes retournées lors d'une résurrection ratée vont à la défausse.
- Six joueurs maximum : au-delà, les tapis adverses ne sont plus lisibles sur un téléphone.

## Où est le code

```
backend/app/games/goulag/
  engine/        règles pures (aucune I/O) : cards, state, game
  spec.py        GameSpec : traduit les messages WebSocket en appels au moteur
  views.py       ce que chaque siège a le droit de voir
  bots.py        Facile (hasard) / Normal (heuristique), cadencement
  tests/         69 tests du moteur, dont 40 parties aléatoires complètes
frontend/src/games/goulag/
  Home.tsx, TablePage.tsx   accueil et cadre de table communs (GameHome, TableFrame, Lobby)
  Table.tsx                 la table : tapis en perspective, sièges, scène centrale, actions, fin de partie
  useChoreography.tsx       rejoue les événements : vols de cartes, scène, impacts, effets d'écran, sons
  socket.ts, types.ts       actions et vue du jeu
frontend/src/app/goulag/        routes : /goulag, /goulag/table/[code]
frontend/src/components/FxLayer.tsx   particules, traînées de tir, ondes de choc, voiles d'écran (commun)
```

## Actions WebSocket du jeu

En plus des actions communes de la plateforme (chat, emote, config, add_bot, remove_bot,
rematch, leave, sync) :

| action | champs | phase |
|---|---|---|
| `ready` | `ready` (bool) | lobby |
| `announce` | `action_kind` : `defend` / `charge` / `attack` | `action`, à son tour |
| `target` | `seat` | `target`, à son tour (soi-même autorisé pour `defend`) ; pioche et révèle |
| `suit` | `suit` : `hearts` / `diamonds` / `clubs` / `spades` | `revival`, par le mort |

## Ce que voit un siège

Public : vies, défense, nombre de charges et état (vivant, œil de faucon) de chacun,
dessus de la défausse, tailles des piles, phase du tour, action annoncée. Privé : la carte
du dessus pour l'œil de faucon (`peek`). Jamais envoyé : les charges (pas même les
siennes), la pioche.

Événements diffusés pour les animations : `game_started`, `turn`, `announced`, `charged`,
`revealed` (la carte piochée, l'action et la cible), `defense_changed`, `attacked` (carte,
charges, total, défense, dégâts), `charges_lost`,
`lives_updated` (cartes retirées / ajoutées), `died`, `suit_chosen`, `revival_flip`
(tentative, carte, succès), `revived`, `eliminated`, `deck_reshuffled`, `game_over`.

## Les bots

| Niveau | Politique |
|---|---|
| Facile | action, cible et couleur au hasard |
| Normal | répare une défense faible, charge un peu puis frappe ; vise une cible qu'il peut tuer, sinon celle qui encaisse le plus ; garde une bonne carte pour sa défense et impose les mauvaises à la défense la plus solide en face ; couleur de résurrection au hasard (compter les couleurs visibles serait un avantage déloyal) |

Les bots décident depuis la vue de leur siège : ils ne voient ni les charges ni la pioche.
