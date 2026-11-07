"""
Sparring bots for gauntlet.py: a spread of playing styles to test model.py
against. Not part of the submission (submit.py only lists what model.py
needs).

Every bot is built from plain-number parameters, so each pickles and plays
in a worker like a real team's bot. StyleBot is one rule set whose
parameters make a nit, a station, a maniac, a trapper and so on;
`random_style(seed)` draws a random one, so the gauntlet can hold back
styles it was never tuned on. ShifterBot changes style mid-match and
CounterBot punishes an opponent that bets or folds too predictably.
"""

import random

from card_utils import evaluate
from player_action import DEALER, PlayerAction
from preflop_data import COMBOS, EQUITY, HANDS

# Share of all combos stronger than each 169-class hand (equity vs random).
_VS_RANDOM = {
    h: sum(COMBOS[j] * EQUITY[i][j] for j in range(len(HANDS)))
    for i, h in enumerate(HANDS)
}
_TOP = {}
_acc = 0
for _h in sorted(HANDS, key=lambda h: -_VS_RANDOM[h]):
    _TOP[_h] = _acc / 1326.0
    _acc += COMBOS[HANDS.index(_h)]


def pf_top(hand) -> float:
    """0.0 for aces, about 1.0 for 72o: the share of hands stronger."""
    a, b = sorted(hand, key=lambda c: c.value, reverse=True)
    if a.rank == b.rank:
        name = a.rank * 2
    else:
        name = a.rank + b.rank + ("s" if a.suit == b.suit else "o")
    return _TOP[name]


AIR, DRAW, WEAK_PAIR, TOP_PAIR, TWO_PAIR, MONSTER = range(6)


def strength(hand, board) -> int:
    """A coarse postflop level for our two cards on this board (AIR ..
    MONSTER), counting only what the hole cards add."""
    cat = evaluate(list(hand) + list(board))[0]
    counts = {}
    for c in board:
        counts[c.value] = counts.get(c.value, 0) + 1
    shape = sorted(counts.values(), reverse=True)
    board_cat = 3 if shape[0] >= 3 else 2 if shape[:2] == [2, 2] else (
        1 if shape[0] == 2 else 0)
    if cat >= 4 and cat > board_cat:
        return MONSTER  # straight or better, or a full house we made
    if cat >= 2 and cat > board_cat:
        return TWO_PAIR  # two pair or trips with a hole card
    if cat >= 1 and cat > board_cat:
        top = max(c.value for c in board)
        mine = [c.value for c in hand]
        if mine[0] == mine[1]:
            return TOP_PAIR if mine[0] > top else WEAK_PAIR
        return TOP_PAIR if top in mine else WEAK_PAIR
    if len(board) < 5:
        cards = list(hand) + list(board)
        for suit in "CDHS":
            if (sum(c.suit == suit for c in cards) >= 4
                    and any(c.suit == suit for c in hand)):
                return DRAW
        values = {c.value for c in cards} | (
            {1} if any(c.value == 14 for c in cards) else set())
        mine = {c.value for c in hand} | (
            {1} if any(c.value == 14 for c in hand) else set())
        for low in range(1, 11):
            run = set(range(low, low + 4))
            if run <= values and run & mine:
                return DRAW
    return AIR


class StyleBot:
    """
    One rule set, many styles. Parameters (all plain numbers):

    open:       raise first in with the top `open` share of hands
    call_pf:    call a raise with the top `call_pf` share
    reraise:    re-raise with the top `reraise` share
    open_x:     open size in big blinds (facing a raise: `reraise_x` x it)
    value:      bet when checked to with this level or better
    bluff:      chance of betting AIR or DRAW anyway
    size:       bet size as a share of the pot
    call_level: call a bet with this level or better
    call_odds:  also call anything when the pot odds are below this
    raise_level: raise a bet with this level or better
    slowplay:   chance of only checking/calling a MONSTER before the river
    """

    DEFAULTS = dict(open=0.5, call_pf=0.4, reraise=0.08, open_x=2.5,
                    reraise_x=3.0, value=TOP_PAIR, bluff=0.2, size=0.66,
                    call_level=TOP_PAIR, call_odds=0.0, raise_level=MONSTER,
                    slowplay=0.0)

    def __init__(self, seed=0, **params):
        self.p = dict(self.DEFAULTS, **params)
        self.rng = random.Random(seed)
        self.hand = []
        self.player_id = None

    def seed(self, hand, player_id):
        self.hand = hand
        self.player_id = player_id

    def _raise(self, gs, total):
        if not gs.can_raise:
            return PlayerAction.call(self.player_id)
        low, high = gs.raise_range
        return PlayerAction.raise_to(
            self.player_id, int(min(high, max(low, round(total)))))

    def _check_fold(self, gs):
        if gs.call_amount == 0:
            return PlayerAction.call(self.player_id)
        return PlayerAction.fold(self.player_id)

    def run(self, actions, gs):
        return self.decide(gs, self.p)

    def decide(self, gs, p):
        me = self.player_id
        if gs.street == "preflop":
            top = pf_top(self.hand)
            raised = gs.current_bet > gs.big_blind
            if not raised:
                if top < p["open"]:
                    return self._raise(gs, p["open_x"] * gs.big_blind)
                return self._check_fold(gs)
            if top < p["reraise"]:
                return self._raise(gs, p["reraise_x"] * gs.current_bet)
            if top < p["call_pf"] or gs.pot_odds < p["call_odds"]:
                return PlayerAction.call(me)
            return self._check_fold(gs)
        level = strength(self.hand, gs.board)
        river = gs.street == "river"
        bet = gs.pot * p["size"]
        if gs.call_amount == 0:
            if level >= MONSTER and not river and (
                    self.rng.random() < p["slowplay"]):
                return PlayerAction.call(me)
            if level >= p["value"] or (
                    level <= DRAW and self.rng.random() < p["bluff"]):
                return self._raise(gs, bet)
            return PlayerAction.call(me)
        if level >= p["raise_level"] and not (
                level >= MONSTER and not river
                and self.rng.random() < p["slowplay"]):
            return self._raise(gs, gs.current_bet + gs.pot)
        if level >= p["call_level"] or gs.pot_odds < p["call_odds"]:
            return PlayerAction.call(me)
        return PlayerAction.fold(me)


def random_style(seed: int) -> StyleBot:
    """A StyleBot with parameters drawn from seed: anything from a nit to
    a maniac. Different seeds make different opponents."""
    r = random.Random(f"style:{seed}")
    open_ = r.uniform(0.15, 0.95)
    return StyleBot(
        seed=seed,
        open=open_,
        call_pf=r.uniform(0.1, 0.9),
        reraise=r.uniform(0.02, 0.3) * open_,
        open_x=r.choice([2.0, 2.5, 3.0, 4.0]),
        reraise_x=r.choice([2.2, 3.0, 4.0]),
        value=r.choice([WEAK_PAIR, TOP_PAIR, TOP_PAIR, TWO_PAIR]),
        bluff=r.uniform(0.0, 0.6),
        size=r.choice([0.33, 0.5, 0.75, 1.0, 1.5]),
        call_level=r.choice([DRAW, WEAK_PAIR, TOP_PAIR, TWO_PAIR]),
        call_odds=r.uniform(0.0, 0.3),
        raise_level=r.choice([TWO_PAIR, MONSTER]),
        slowplay=r.uniform(0.0, 0.5),
    )


# Hand-written styles.
STATION = dict(open=0.25, call_pf=0.85, reraise=0.03, value=TWO_PAIR,
               bluff=0.0, size=0.5, call_level=DRAW, call_odds=0.3,
               raise_level=MONSTER)
MANIAC = dict(open=0.85, call_pf=0.7, reraise=0.35, open_x=3.0,
              reraise_x=3.0, value=WEAK_PAIR, bluff=0.65, size=1.0,
              call_level=WEAK_PAIR, call_odds=0.2, raise_level=TOP_PAIR)
TRAPPER = dict(open=0.3, call_pf=0.35, reraise=0.04, value=TWO_PAIR,
               bluff=0.05, size=0.75, call_level=TOP_PAIR, call_odds=0.15,
               raise_level=TWO_PAIR, slowplay=0.8)
NIT = dict(open=0.15, call_pf=0.12, reraise=0.04, value=TWO_PAIR,
           bluff=0.02, size=0.75, call_level=TWO_PAIR, call_odds=0.0,
           raise_level=MONSTER)


class ShifterBot(StyleBot):
    """Plays one style for `switch` hands, then another: a nit that turns
    maniac by default. Punishes a read that never updates."""

    def __init__(self, seed=0, first=None, then=None, switch=300):
        super().__init__(seed)
        self.first = dict(StyleBot.DEFAULTS, **(first or NIT))
        self.then = dict(StyleBot.DEFAULTS, **(then or MANIAC))
        self.switch = switch
        self.hands_played = 0

    def seed(self, hand, player_id):
        super().seed(hand, player_id)
        self.hands_played += 1

    def run(self, actions, gs):
        p = self.first if self.hands_played <= self.switch else self.then
        return self.decide(gs, p)


class CounterBot(StyleBot):
    """
    A solid default that adapts to the opponent's own habits: if they bet
    most times they are checked to, it calls down lighter and check-raises
    draws; if they fold to most bets, it bluffs more. Punishes an exploit
    that is too predictable.
    """

    def __init__(self, seed=0):
        super().__init__(seed, open=0.5, call_pf=0.4, reraise=0.1,
                         value=TOP_PAIR, bluff=0.2, size=0.66,
                         call_level=TOP_PAIR, call_odds=0.1,
                         raise_level=TWO_PAIR)
        self.opp_bets, self.opp_chances = 0, 0
        self.opp_folds, self.opp_faced = 0, 0
        self.board = 0  # board cards seen this hand
        self.bet_open = False  # a postflop bet is waiting for an answer

    def seed(self, hand, player_id):
        super().seed(hand, player_id)
        self.board = 0
        self.bet_open = False

    def _learn(self, actions):
        """Counts the other player's postflop bets (when nothing is owed)
        and folds (when facing a bet)."""
        for a in actions:
            if a.player_id == DEALER:
                if a.kind == "reveal_card":
                    self.board += 1
                    self.bet_open = False
                continue
            if self.board < 3 or a.kind not in ("fold", "call", "raise"):
                continue
            if a.player_id != self.player_id:
                if self.bet_open:
                    self.opp_faced += 1
                    self.opp_folds += a.kind == "fold"
                else:
                    self.opp_chances += 1
                    self.opp_bets += a.kind == "raise"
            self.bet_open = a.kind == "raise"

    def run(self, actions, gs):
        self._learn(actions)
        p = dict(self.p)
        bet_rate = (self.opp_bets + 2) / (self.opp_chances + 5)
        fold_rate = (self.opp_folds + 2) / (self.opp_faced + 5)
        if bet_rate > 0.6:  # they bet too often: call down, trap draws
            p.update(call_level=WEAK_PAIR, call_odds=0.3,
                     raise_level=TOP_PAIR, slowplay=0.5)
        if fold_rate > 0.55:  # they fold too often: bluff more
            p.update(bluff=0.6, size=0.75)
        elif fold_rate < 0.3:  # they never fold: value only
            p.update(bluff=0.0, value=TOP_PAIR)
        return self.decide(gs, p)

    def end_game(self, actions, gs):
        self._learn(actions)
