"""Moteur de règles du Nine to One — pur et server-authoritative.

Toutes les fonctions mutent un GameState et lèvent GameError (ou sous-classe)
sur coup illégal. Aucune I/O ici : la couche réseau appelle, persiste, diffuse.

Les fonctions d'action renvoient une liste d'événements (dicts) décrivant ce qui
s'est passé (coupe, ramassage, fin de partie...), pour les animations côté client.

Décisions d'arbitrage sur les zones floues des règles officielles
(docs/regles-officielles.txt) :
- Le premier joueur est celui qui détient en main la plus petite carte hors 2
  (égalité entre plusieurs joueurs : tirage au sort) ; il joue ce qu'il veut.
- Une contrainte active (7 ou 9) s'applique à toutes les cartes sauf le 2 :
  un 9 n'est pas jouable sur un « 7 inférieur », un 10 n'est jouable sous
  aucune contrainte « inférieur ».
- Après un ramassage (joueur bloqué), le joueur dont le coup a bloqué rejoue.
  Cela vaut aussi pour une carte cachée retournée injouable.
- « Bonne pioche » (chase_*) : après avoir posé, tant que personne n'a agi,
  on peut enchaîner d'autres cartes de la même valeur — fraîchement piochées,
  ou une carte cachée retournée vite (ratée : elle reste en main). Les cartes
  visibles complètent aussi un coup qui vide la main, sans limite de temps.
"""

from __future__ import annotations

import random

from .cards import shuffled_deck
from .errors import IllegalMove, InvalidAction, NotYourTurn
from .state import Comparator, Constraint, GameState, GameStatus, PlayerState

MIN_PLAYERS = 2
MAX_PLAYERS = 5
HAND_SIZE = 3

Event = dict


# ---------------------------------------------------------------------------
# Mise en place
# ---------------------------------------------------------------------------


def create_game(creator_name: str, seed: int | None = None) -> GameState:
    """Crée une partie en lobby avec son premier joueur, cartes distribuées."""
    state = GameState(players=[], draw_pile=shuffled_deck(seed))
    add_player(state, creator_name)
    return state


def add_player(state: GameState, name: str) -> None:
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("La partie a déjà commencé.")
    if len(state.players) >= MAX_PLAYERS:
        raise InvalidAction("La partie est pleine.")
    if any(p.name == name for p in state.players):
        raise InvalidAction("Ce pseudo est déjà pris dans cette partie.")
    player = PlayerState(
        name=name,
        face_down=[state.draw_pile.pop() for _ in range(HAND_SIZE)],
        face_up=[state.draw_pile.pop() for _ in range(HAND_SIZE)],
        hand=[state.draw_pile.pop() for _ in range(HAND_SIZE)],
    )
    _sort_hand(player)
    state.players.append(player)


def _sort_hand(player: PlayerState) -> None:
    """La main est toujours triée du 2 à l'As (les zones posées gardent leur place)."""
    player.hand.sort(key=lambda c: (c.value, c.suit.value))


def remove_player(state: GameState, player_index: int) -> None:
    """Retire un joueur du lobby ; ses cartes retournent dans la pioche, remélangée.

    (Remélange nécessaire : le joueur partant a vu ses 9 cartes.)
    """
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("Impossible de retirer un joueur d'une partie commencée.")
    player = state.players.pop(player_index)
    state.draw_pile.extend(player.hand + player.face_up + player.face_down)
    random.shuffle(state.draw_pile)


def swap_cards(state: GameState, player_index: int, hand_index: int, face_up_index: int) -> None:
    """Échange initial : une carte de la main contre une carte visible."""
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("Les échanges ne sont possibles qu'avant le début de la partie.")
    player = state.players[player_index]
    if player.ready:
        raise InvalidAction("Impossible d'échanger après s'être déclaré prêt.")
    if not (0 <= hand_index < len(player.hand) and 0 <= face_up_index < len(player.face_up)):
        raise InvalidAction("Indice d'échange invalide.")
    player.hand[hand_index], player.face_up[face_up_index] = (
        player.face_up[face_up_index],
        player.hand[hand_index],
    )
    _sort_hand(player)


def set_ready(state: GameState, player_index: int, ready: bool = True) -> list[Event]:
    """Déclare un joueur prêt ; démarre la partie quand tout le monde l'est."""
    if state.status is not GameStatus.LOBBY:
        raise InvalidAction("La partie a déjà commencé.")
    state.players[player_index].ready = ready
    if len(state.players) >= MIN_PLAYERS and all(p.ready for p in state.players):
        return _start(state)
    return []


def _start(state: GameState) -> list[Event]:
    state.status = GameStatus.PLAYING
    # Le détenteur de la plus petite carte hors 2 ouvre — il joue ce qu'il veut.
    # Plusieurs détenteurs à égalité : tirage au sort entre eux.
    best_value: int | None = None
    holders: list[int] = []
    for i, player in enumerate(state.players):
        for card in player.hand:
            if card.value == 2:
                continue
            if best_value is None or card.value < best_value:
                best_value = card.value
                holders = [i]
            elif card.value == best_value and i not in holders:
                holders.append(i)
    state.turn_index = random.choice(holders) if holders else 0
    return [{"type": "game_started", "first_player": state.turn_index, "first_value": best_value}]


# ---------------------------------------------------------------------------
# Légalité des coups
# ---------------------------------------------------------------------------


def can_play_value(state: GameState, value: int) -> bool:
    """La valeur est-elle posable sur le tas central dans l'état courant ?"""
    if value == 2:
        return True
    if state.constraint is not None:
        return state.constraint.allows(value)
    if not state.pile:
        return True
    if value == 10:
        return True
    return value >= state.pile[-1].value


def playable_values(state: GameState, player_index: int) -> set[int]:
    """Valeurs jouables depuis la main du joueur (vide => il doit ramasser ou retourner)."""
    player = state.players[player_index]
    return {c.value for c in player.hand if can_play_value(state, c.value)}


# ---------------------------------------------------------------------------
# Actions de jeu
# ---------------------------------------------------------------------------


def play_cards(
    state: GameState,
    player_index: int,
    value: int,
    count: int = 1,
    direction: Comparator | None = None,
) -> list[Event]:
    """Pose `count` cartes de valeur `value` depuis la main du joueur.

    Si la pose vide entièrement la main, les cartes visibles de même valeur
    peuvent compléter le coup (la main enchaîne naturellement sur les visibles).
    """
    _check_turn(state, player_index)
    player = state.players[player_index]
    if count < 1:
        raise IllegalMove("Il faut poser au moins une carte.")
    matching = [c for c in player.hand if c.value == value]
    from_face_up: list = []
    if count > len(matching):
        # Complément depuis les cartes visibles, uniquement si toute la main part.
        if len(matching) < len(player.hand):
            raise IllegalMove("Vous n'avez pas assez de cartes de cette valeur.")
        needed = count - len(matching)
        from_face_up = [c for c in player.face_up if c.value == value][:needed]
        if len(from_face_up) < needed:
            raise IllegalMove("Vous n'avez pas assez de cartes de cette valeur.")
    if not can_play_value(state, value):
        raise IllegalMove("Cette carte ne peut pas être posée maintenant.")
    if value == 7 and direction not in (Comparator.GTE, Comparator.LTE):
        raise IllegalMove("Poser un 7 impose de choisir : au-dessus ou en dessous.")

    events: list[Event] = []
    played = matching[: count - len(from_face_up)] + from_face_up
    for card in played:
        if card in player.hand:
            player.hand.remove(card)
        else:
            player.face_up.remove(card)
        state.pile.append(card)
    state.last_play_index = player_index
    events.append(
        {
            "type": "cards_played",
            "player": player_index,
            "value": value,
            "count": count,
            # Les cartes exactes, pour que le client anime leur vol.
            "cards": [c.to_dict() for c in played],
        }
    )

    # Effet de la carte posée.
    if value == 7:
        state.constraint = Constraint(direction, 7)
    elif value == 9:
        state.constraint = Constraint(Comparator.LTE, 9)
    else:
        state.constraint = None

    # Coupe : 10, ou 4 cartes identiques qui se suivent sur le tas.
    cut = value == 10 or _four_in_a_row(state)
    if cut:
        state.discard.extend(state.pile)
        state.pile.clear()
        state.constraint = None
        events.append({"type": "pile_cut", "player": player_index})

    before_draw = {(c.value, c.suit) for c in player.hand}
    draw_before = len(state.draw_pile)
    events.extend(_finish_move(state, player_index, replay=cut))
    _arm_chase(state, player, value, before_draw, draw_before)
    return events


def _arm_chase(
    state: GameState,
    player: PlayerState,
    value: int,
    before_draw: set,
    draw_before: int,
) -> None:
    """Arme la « bonne pioche » si la pioche du coup a fourni la valeur posée."""
    state.chase_armed = False
    if len(state.draw_pile) >= draw_before:
        return  # rien pioché (les visibles passées en main ne comptent pas)
    for card in player.hand:
        if card.value == value and (card.value, card.suit) not in before_draw:
            state.chase_armed = True
            return


def flip_face_down(state: GameState, player_index: int, face_down_index: int) -> list[Event]:
    """Retourne une carte cachée (phase finale) : elle devient la main du joueur.

    Si elle est injouable, le joueur ramasse le tas (carte incluse) et le joueur
    précédent rejoue. Sinon elle reste en main, à jouer via play_cards.
    """
    _check_turn(state, player_index)
    player = state.players[player_index]
    if player.hand or player.face_up:
        raise InvalidAction("Il reste des cartes jouables : impossible de retourner une cachée.")
    if not (0 <= face_down_index < len(player.face_down)):
        raise InvalidAction("Indice de carte cachée invalide.")

    card = player.face_down.pop(face_down_index)
    player.hand.append(card)
    state.chase_armed = False  # quelqu'un a agi : la fenêtre d'enchaînement se ferme
    events: list[Event] = [{"type": "card_flipped", "player": player_index, "card": card.to_dict()}]
    if not can_play_value(state, card.value):
        events.extend(_pickup(state, player_index))
    return events


def chase_value(state: GameState, player_index: int) -> int | None:
    """Valeur enchaînable hors tour, ou None.

    « Bonne pioche » : le dernier poseur peut immédiatement rajouter la carte
    qu'il vient de piocher si elle a la même valeur, ou retourner vite une carte
    cachée quand il n'a plus rien d'autre — tant que personne n'a agi depuis.
    Une carte identique déjà en main avant le coup ne compte pas.
    """
    if state.status is not GameStatus.PLAYING:
        return None
    if state.last_play_index != player_index or not state.pile:
        return None
    player = state.players[player_index]
    if player.finished:
        return None
    value = state.pile[-1].value
    if player.hand:
        return value if state.chase_armed else None
    if player.face_up:
        return None  # les visibles se posent avec le coup, pas après
    return value if player.face_down else None


def chase_play(state: GameState, player_index: int, count: int = 1) -> list[Event]:
    """Enchaîne `count` cartes de la valeur tout juste posée, hors tour."""
    value = chase_value(state, player_index)
    if value is None:
        raise IllegalMove("Trop tard : le coup ne peut plus être enchaîné.")
    player = state.players[player_index]
    if count < 1:
        raise IllegalMove("Il faut poser au moins une carte.")
    matching = [c for c in player.hand if c.value == value]
    from_face_up: list = []
    if count > len(matching):
        if len(matching) < len(player.hand):
            raise IllegalMove("Vous n'avez pas assez de cartes de cette valeur.")
        needed = count - len(matching)
        from_face_up = [c for c in player.face_up if c.value == value][:needed]
        if len(from_face_up) < needed:
            raise IllegalMove("Vous n'avez pas assez de cartes de cette valeur.")

    played = matching[: count - len(from_face_up)] + from_face_up
    for card in played:
        if card in player.hand:
            player.hand.remove(card)
        else:
            player.face_up.remove(card)
        state.pile.append(card)
    events: list[Event] = [
        {
            "type": "cards_played",
            "player": player_index,
            "value": value,
            "count": len(played),
            "cards": [c.to_dict() for c in played],
            "chase": True,
        }
    ]
    # La contrainte en vigueur vient déjà de cette valeur : elle ne change pas.
    before_draw = {(c.value, c.suit) for c in player.hand}
    draw_before = len(state.draw_pile)
    events.extend(_finish_chase(state, player_index))
    _arm_chase(state, player, value, before_draw, draw_before)
    return events


def chase_flip(state: GameState, player_index: int, face_down_index: int) -> list[Event]:
    """Retourne vite une carte cachée après avoir posé sa dernière carte :
    si elle a la même valeur, elle part sur le tas ; sinon elle reste en main."""
    value = chase_value(state, player_index)
    if value is None:
        raise IllegalMove("Trop tard : le coup ne peut plus être enchaîné.")
    player = state.players[player_index]
    if player.hand or player.face_up:
        raise InvalidAction("Il reste des cartes jouables : impossible de retourner une cachée.")
    if not (0 <= face_down_index < len(player.face_down)):
        raise InvalidAction("Indice de carte cachée invalide.")

    card = player.face_down.pop(face_down_index)
    events: list[Event] = [
        {"type": "card_flipped", "player": player_index, "card": card.to_dict(), "chase": True}
    ]
    if card.value != value:
        # Raté : la carte révélée devient sa main, il l'assumera à son tour.
        player.hand.append(card)
        return events
    state.pile.append(card)
    events.append(
        {
            "type": "cards_played",
            "player": player_index,
            "value": value,
            "count": 1,
            "cards": [card.to_dict()],
            "chase": True,
        }
    )
    return events + _finish_chase(state, player_index)


def _finish_chase(state: GameState, player_index: int) -> list[Event]:
    """Suites d'un enchaînement : coupe éventuelle, pioche, fin, blocage du joueur au trait."""
    events: list[Event] = []
    cut = state.pile and state.pile[-1].value == 10 or _four_in_a_row(state)
    if cut:
        state.discard.extend(state.pile)
        state.pile.clear()
        state.constraint = None
        events.append({"type": "pile_cut", "player": player_index})

    settle_events, game_over = _settle_player(state, player_index)
    events.extend(settle_events)
    if game_over:
        return events

    if cut:
        if not state.players[player_index].finished:
            state.turn_index = player_index  # il rejoue, comme pour toute coupe
        else:
            state.turn_index = _next_active(state, player_index)
        return events

    # Le tas a changé sous les pieds du joueur au trait : s'il est bloqué, il ramasse.
    current = state.current_player
    if current.hand and not playable_values(state, state.turn_index):
        events.extend(_pickup(state, state.turn_index))
    return events


# ---------------------------------------------------------------------------
# Mécanique interne
# ---------------------------------------------------------------------------


def _check_turn(state: GameState, player_index: int) -> None:
    if state.status is not GameStatus.PLAYING:
        raise InvalidAction("La partie n'est pas en cours.")
    if state.turn_index != player_index:
        raise NotYourTurn("Ce n'est pas votre tour.")


def _four_in_a_row(state: GameState) -> bool:
    if len(state.pile) < 4:
        return False
    return len({c.value for c in state.pile[-4:]}) == 1


def _draw_up_to_hand_size(state: GameState, player: PlayerState) -> None:
    drew = False
    while len(player.hand) < HAND_SIZE and state.draw_pile:
        player.hand.append(state.draw_pile.pop())
        drew = True
    if drew:
        _sort_hand(player)


def _update_phase(player: PlayerState) -> None:
    """Main vide et pioche épuisée : les cartes visibles deviennent la main."""
    if not player.hand and player.face_up:
        player.hand, player.face_up = player.face_up, []
        _sort_hand(player)


def _settle_player(state: GameState, player_index: int) -> tuple[list[Event], bool]:
    """Pioche, transition de phase et détection de fin pour un joueur qui vient
    de poser. Renvoie (événements, partie terminée)."""
    player = state.players[player_index]
    events: list[Event] = []

    _draw_up_to_hand_size(state, player)
    _update_phase(player)

    if player.card_count == 0:
        state.ranks_assigned += 1
        player.finish_rank = state.ranks_assigned
        events.append(
            {"type": "player_finished", "player": player_index, "rank": player.finish_rank}
        )

    active = state.active_indices()
    if len(active) <= 1:
        state.status = GameStatus.FINISHED
        if active:
            loser = active[0]
            state.ranks_assigned += 1
            state.players[loser].finish_rank = state.ranks_assigned
            events.append({"type": "game_over", "loser": loser})
        return events, True
    return events, False


def _finish_move(state: GameState, player_index: int, replay: bool) -> list[Event]:
    """Pioche, transitions de phase, détection de fin, puis passage de tour."""
    events, game_over = _settle_player(state, player_index)
    if game_over:
        return events
    if replay and not state.players[player_index].finished:
        # Coupe : le joueur rejoue immédiatement, le tas est vide.
        return events
    events.extend(_advance_turn(state, from_index=player_index))
    return events


def _advance_turn(state: GameState, from_index: int) -> list[Event]:
    """Passe au joueur actif suivant, en résolvant un éventuel ramassage forcé."""
    state.turn_index = _next_active(state, from_index)
    nxt = state.current_player
    # Main non vide et aucun coup légal : ramassage automatique du tas.
    if nxt.hand and not playable_values(state, state.turn_index):
        return _pickup(state, state.turn_index)
    # Main vide (phase des cartes cachées) : on attend son flip_face_down.
    return []


def _pickup(state: GameState, player_index: int) -> list[Event]:
    """Le joueur ramasse le tas central ; celui qui a provoqué le blocage rejoue."""
    player = state.players[player_index]
    player.hand.extend(state.pile)
    _sort_hand(player)
    state.pile.clear()
    state.constraint = None
    events: list[Event] = [{"type": "pile_picked_up", "player": player_index}]

    replay_index = state.last_play_index
    if replay_index is None or state.players[replay_index].finished:
        base = replay_index if replay_index is not None else player_index
        state.turn_index = _next_active(state, base)
    else:
        state.turn_index = replay_index
    return events


def _next_active(state: GameState, from_index: int) -> int:
    n = len(state.players)
    for step in range(1, n + 1):
        candidate = (from_index + step) % n
        if not state.players[candidate].finished:
            return candidate
    raise InvalidAction("Aucun joueur actif.")  # ne devrait jamais arriver
