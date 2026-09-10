"""Moteur de règles du Goulag — pur et server-authoritative.

Toutes les fonctions mutent un GameState et lèvent GameError (ou sous-classe) sur
coup illégal. Aucune I/O ici. Les fonctions d'action renvoient une liste
d'événements (dicts) décrivant ce qui s'est passé, pour les animations côté client.

Règles (docs/goulag/README.md) et arbitrages retenus :
- Le joueur annonce son action (défense, charge, attaque) puis, pour une défense ou
  une attaque, désigne sa cible (défense : lui-même ou un autre ; attaque : un autre),
  le tout sans avoir vu la carte : elle n'est piochée et révélée qu'une fois la cible
  choisie. « Œil de faucon » (un seul As de vie) voit la carte avant d'annoncer.
- Dégâts = attaque (carte + charges) − défense de la cible ; rien ne passe si ≤ 0.
  La défense n'est jamais consommée. Les cartes jouées vont à la défausse avant
  toute recherche de carte de remplacement.
- Une attaque qui touche les vies fait perdre ses charges au défenseur.
- Recomposition des vies après dégâts : si l'une des cartes de vie vaut exactement le
  nouveau total, elle reste seule ; sinon on garde la plus forte et on cherche la
  carte exacte du complément (défausse d'abord, puis pioche) ; si le nouveau total
  est inférieur ou égal à la plus forte, une seule carte de la valeur exacte. À défaut
  de carte exacte, deux cartes qui font la somme ; à défaut encore, la plus petite
  carte au-dessus (le blessé y gagne, événement lives_rounded_up).
- La pioche ne se régénère qu'au moment où sa dernière carte est tirée : la défausse
  est alors mélangée pour former la nouvelle pioche.
- Mort : les vies partent à la défausse, le mort choisit une couleur, on retourne le
  dessus de la pioche ; bonne couleur → il revit avec cette carte pour unique vie
  (sa défense reste en place ; ses charges sont déjà perdues, l'attaque a touché ses
  vies). Sinon on coupe la pioche et on retourne la carte
  du milieu, même couleur ; bonne → il revit avec ; sinon éliminé. Les cartes
  retournées ratées, sa défense et ses charges vont à la défausse. Le tour suivant
  est celui du voisin de l'attaquant : personne ne saute son tour.
- Premier joueur : plus petite défense, puis moins de vies, puis tirage au sort.
"""

from __future__ import annotations

from .cards import Card, Suit, shuffled_deck
from .errors import IllegalMove, InvalidAction, NotYourTurn
from .state import Action, GameState, GameStatus, Phase, PlayerState

MIN_PLAYERS = 2
MAX_PLAYERS = 6
DEAL_SIZE = 3
MAX_CHARGES = 2

Event = dict


# ---------------------------------------------------------------------------
# Mise en place
# ---------------------------------------------------------------------------


def create_game(creator_name: str, seed: int | None = None) -> GameState:
    """Crée une partie en lobby avec son premier joueur."""
    state = GameState(players=[])
    if seed is not None:
        state.rng.seed(seed)
    add_player(state, creator_name)
    return state


def add_player(state: GameState, name: str) -> None:
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("La partie a déjà commencé.")
    if len(state.players) >= MAX_PLAYERS:
        raise InvalidAction("La partie est pleine.")
    if any(p.name == name for p in state.players):
        raise InvalidAction("Ce pseudo est déjà pris dans cette partie.")
    state.players.append(PlayerState(name=name))


def remove_player(state: GameState, player_index: int) -> None:
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("Impossible de quitter une partie en cours.")
    del state.players[player_index]


def set_ready(state: GameState, player_index: int, ready: bool = True) -> list[Event]:
    """Déclare un joueur prêt ; distribue et démarre quand tout le monde l'est."""
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("La partie a déjà commencé.")
    state.players[player_index].ready = ready
    if len(state.players) >= MIN_PLAYERS and all(p.ready for p in state.players):
        return _start(state)
    return []


def _start(state: GameState) -> list[Event]:
    state.draw_pile = shuffled_deck(state.rng)
    state.discard = []
    for player in state.players:
        hand = sorted((state.draw_pile.pop() for _ in range(DEAL_SIZE)), key=lambda c: c.value)
        player.defense = hand[0]
        player.lives = [hand[2], hand[1]]  # la plus forte à gauche
        player.charges = []
        player.finish_rank = None
    state.status = GameStatus.PLAYING
    state.eliminated = 0
    state.phase = Phase.ACTION
    # Plus petite défense, puis moins de vies, puis tirage au sort.
    key = lambda i: (state.players[i].defense.value, state.players[i].life_total)  # noqa: E731
    best = min(key(i) for i in range(len(state.players)))
    candidates = [i for i in range(len(state.players)) if key(i) == best]
    state.turn_index = state.rng.choice(candidates)
    return [
        {"type": "game_started", "first_player": state.turn_index},
        {"type": "turn", "player": state.turn_index},
    ]


# ---------------------------------------------------------------------------
# Le tour : annoncer, voir, cibler
# ---------------------------------------------------------------------------


def peek(state: GameState, player_index: int) -> Card | None:
    """La carte du dessus, pour l'« œil de faucon » au trait (sinon None)."""
    if (
        state.status is not GameStatus.PLAYING
        or state.phase is not Phase.ACTION
        or state.turn_index != player_index
        or not state.players[player_index].hawk_eye
    ):
        return None
    return state.draw_pile[-1] if state.draw_pile else None


def can_charge(state: GameState, player_index: int) -> bool:
    return len(state.players[player_index].charges) < MAX_CHARGES


def announce(state: GameState, player_index: int, action: Action) -> list[Event]:
    """Le joueur au trait annonce son action, à l'aveugle.

    Charge : il pioche et pose aussitôt. Défense / attaque : le tour passe en phase
    TARGET, la carte n'est piochée qu'une fois la cible désignée.
    """
    _check_turn(state, player_index, Phase.ACTION)
    player = state.players[player_index]
    if action is Action.CHARGE and not can_charge(state, player_index):
        raise IllegalMove("Deux charges maximum.")
    if action is Action.CHARGE:
        card, events = _draw(state)
        player.charges.append(card)
        events.append({"type": "charged", "player": player_index, "charges": len(player.charges)})
        events.extend(_end_turn(state))
        return events
    state.phase = Phase.TARGET
    state.pending_action = action
    return [{"type": "announced", "player": player_index, "action": action.value}]


def choose_target(state: GameState, player_index: int, target_index: int) -> list[Event]:
    """La cible désignée, on pioche et on révèle : la défense change, ou l'attaque frappe."""
    _check_turn(state, player_index, Phase.TARGET)
    if not (0 <= target_index < len(state.players)) or not state.players[target_index].alive:
        raise InvalidAction("Cible invalide.")
    action = state.pending_action
    assert action is not None
    if action is Action.ATTACK and target_index == player_index:
        raise InvalidAction("On ne s'attaque pas soi-même.")
    state.pending_action = None
    card, events = _draw(state)
    events.append(
        {
            "type": "revealed",
            "player": player_index,
            "target": target_index,
            "action": action.value,
            "card": card.to_dict(),
        }
    )
    if action is Action.DEFEND:
        events.extend(_defend(state, player_index, target_index, card))
    else:
        events.extend(_attack(state, player_index, target_index, card))
    if state.phase is not Phase.REVIVAL:
        events.extend(_end_turn(state))
    return events


def _defend(state: GameState, player_index: int, target_index: int, card: Card) -> list[Event]:
    target = state.players[target_index]
    old = target.defense
    target.defense = card
    if old is not None:
        state.discard.append(old)
    return [
        {
            "type": "defense_changed",
            "player": player_index,
            "target": target_index,
            "card": card.to_dict(),
            "old": old.to_dict() if old else None,
        }
    ]


def _attack(state: GameState, player_index: int, target_index: int, card: Card) -> list[Event]:
    attacker = state.players[player_index]
    target = state.players[target_index]
    charges = attacker.charges
    attacker.charges = []
    total = card.value + sum(c.value for c in charges)
    assert target.defense is not None
    damage = max(0, total - target.defense.value)
    # Les cartes jouées vont à la défausse avant toute recherche de remplacement.
    state.discard.append(card)
    state.discard.extend(charges)
    events: list[Event] = [
        {
            "type": "attacked",
            "player": player_index,
            "target": target_index,
            "card": card.to_dict(),
            "charges": [c.to_dict() for c in charges],
            "total": total,
            "defense": target.defense.value,
            "damage": damage,
        }
    ]
    if damage <= 0:
        return events
    if target.charges:
        state.discard.extend(target.charges)
        target.charges = []
        events.append({"type": "charges_lost", "player": target_index})
    remaining = target.life_total - damage
    if remaining <= 0:
        events.extend(_die(state, target_index))
        return events
    events.extend(_set_lives(state, target_index, remaining))
    return events


# ---------------------------------------------------------------------------
# Vies : recomposition après dégâts
# ---------------------------------------------------------------------------


def _set_lives(state: GameState, player_index: int, total: int) -> list[Event]:
    """Recompose les cartes de vie pour afficher `total` (> 0)."""
    player = state.players[player_index]
    old = list(player.lives)
    events: list[Event] = []
    exact = next((c for c in old if c.value == total), None)
    if exact is not None:
        new = [exact]
    else:
        strongest = max(old, key=lambda c: c.value)
        if total > strongest.value:
            new = [strongest, *_find_cards(state, total - strongest.value, events)]
        else:
            new = _find_cards(state, total, events)
    for card in old:
        if card not in new:
            state.discard.append(card)
    player.lives = sorted(new, key=lambda c: -c.value)
    return events + [
        {
            "type": "lives_updated",
            "player": player_index,
            "total": player.life_total,
            "lives": [c.to_dict() for c in player.lives],
            "removed": [c.to_dict() for c in old if c not in new],
            "added": [c.to_dict() for c in new if c not in old],
        }
    ]


def _find_cards(state: GameState, total: int, events: list[Event]) -> list[Card]:
    """Une carte de la valeur exacte (défausse d'abord, puis pioche), sinon deux cartes
    qui font la somme."""
    card = _take_value(state, total, events)
    if card is not None:
        return [card]
    for high in range(min(total - 1, 13), 0, -1):
        first = _take_value(state, high, events)
        if first is None:
            continue
        second = _take_value(state, total - high, events)
        if second is not None:
            return [first, second]
        state.discard.append(first)
    # Aucune combinaison exacte disponible (par exemple les quatre As déjà en jeu alors
    # qu'il faut 1) : la plus petite carte au-dessus, au bénéfice du blessé. Les piles
    # ne peuvent pas être vides toutes les deux (30 cartes en jeu au maximum).
    for value in range(total + 1, 14):
        card = _take_value(state, value, events)
        if card is not None:
            events.append({"type": "lives_rounded_up", "wanted": total, "got": value})
            return [card]
    return []


def _take_value(state: GameState, value: int, events: list[Event]) -> Card | None:
    """Retire une carte de cette valeur : défausse en priorité, sinon pioche."""
    for pile in (state.discard, state.draw_pile):
        for i in range(len(pile) - 1, -1, -1):
            if pile[i].value == value:
                card = pile.pop(i)
                events.extend(_refill_if_empty(state))
                return card
    return None


# ---------------------------------------------------------------------------
# Mort, résurrection, élimination
# ---------------------------------------------------------------------------


def _die(state: GameState, player_index: int) -> list[Event]:
    player = state.players[player_index]
    state.discard.extend(player.lives)
    player.lives = []
    state.phase = Phase.REVIVAL
    state.reviving = player_index
    return [{"type": "died", "player": player_index}]


def choose_suit(state: GameState, player_index: int, suit: Suit) -> list[Event]:
    """Le mort choisit sa couleur : première carte, puis coupe du paquet si besoin."""
    if state.status is not GameStatus.PLAYING or state.phase is not Phase.REVIVAL:
        raise InvalidAction("Personne n'a de couleur à choisir.")
    if state.reviving != player_index:
        raise NotYourTurn("Ce n'est pas à toi de choisir.")
    events: list[Event] = [{"type": "suit_chosen", "player": player_index, "suit": suit.value}]

    first, draw_events = _draw(state)
    events.extend(draw_events)
    events.append(
        {
            "type": "revival_flip",
            "player": player_index,
            "attempt": 1,
            "card": first.to_dict(),
            "success": first.suit is suit,
        }
    )
    if first.suit is suit:
        return events + _revive(state, player_index, first)
    state.discard.append(first)

    # Seconde chance : on coupe la pioche et on retourne la carte du milieu.
    middle = len(state.draw_pile) // 2
    second = state.draw_pile.pop(middle)
    events.extend(_refill_if_empty(state))
    events.append(
        {
            "type": "revival_flip",
            "player": player_index,
            "attempt": 2,
            "card": second.to_dict(),
            "success": second.suit is suit,
        }
    )
    if second.suit is suit:
        return events + _revive(state, player_index, second)
    state.discard.append(second)
    return events + _eliminate(state, player_index)


def _revive(state: GameState, player_index: int, card: Card) -> list[Event]:
    player = state.players[player_index]
    player.lives = [card]
    state.phase = Phase.ACTION
    state.reviving = None
    return [{"type": "revived", "player": player_index, "card": card.to_dict()}, *_end_turn(state)]


def _eliminate(state: GameState, player_index: int) -> list[Event]:
    """Le joueur sort : ce qu'il lui restait (défense, charges) retourne en jeu."""
    player = state.players[player_index]
    defense = player.defense
    if defense is not None:
        state.discard.append(defense)
    player.defense = None
    state.discard.extend(player.charges)
    player.charges = []
    state.eliminated += 1
    player.finish_rank = len(state.players) - state.eliminated + 1
    state.phase = Phase.ACTION
    state.reviving = None
    events: list[Event] = [
        {
            "type": "eliminated",
            "player": player_index,
            "rank": player.finish_rank,
            "defense": defense.to_dict() if defense else None,
        }
    ]
    alive = state.alive_indices()
    if len(alive) == 1:
        state.players[alive[0]].finish_rank = 1
        state.status = GameStatus.FINISHED
        events.append({"type": "game_over", "ranks": [p.finish_rank for p in state.players]})
        return events
    events.extend(_end_turn(state))
    return events


# ---------------------------------------------------------------------------
# Pioche et tours
# ---------------------------------------------------------------------------


def _draw(state: GameState) -> tuple[Card, list[Event]]:
    card = state.draw_pile.pop()
    return card, _refill_if_empty(state)


def _refill_if_empty(state: GameState) -> list[Event]:
    """La dernière carte vient d'être prise : la défausse mélangée devient la pioche."""
    if state.draw_pile or not state.discard:
        return []
    state.draw_pile = list(state.discard)
    state.discard = []
    state.rng.shuffle(state.draw_pile)
    return [{"type": "deck_reshuffled", "count": len(state.draw_pile)}]


def _end_turn(state: GameState) -> list[Event]:
    if state.status is not GameStatus.PLAYING:
        return []
    state.phase = Phase.ACTION
    n = len(state.players)
    i = state.turn_index
    for _ in range(n):
        i = (i + 1) % n
        if state.players[i].alive:
            break
    state.turn_index = i
    return [{"type": "turn", "player": i}]


def _check_turn(state: GameState, player_index: int, phase: Phase) -> None:
    if state.status is not GameStatus.PLAYING:
        raise InvalidAction("La partie n'est pas en cours.")
    if state.phase is not phase:
        raise InvalidAction("Ce n'est pas le moment.")
    if state.turn_index != player_index:
        raise NotYourTurn("Ce n'est pas ton tour.")
