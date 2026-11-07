"""
Checks the Phase 1 opponent profiler (not part of the submission).

    .venv/bin/python check_profiler.py

1. Scripted hands with known answers: exact counter asserts.
2. Profiles every dummy over many hands and prints stats and label.
"""

import random
import sys

from arena.dummies import DUMMIES
from card_utils import full_deck
from engine import play_hand
from model import Model
from player_action import PlayerAction


class Script:
    """Plays a fixed list of moves ("f", "c", or an int raise total)."""

    def __init__(self, moves):
        self.moves = list(moves)

    def seed(self, hand, player_id):
        self.player_id = player_id

    def run(self, actions, game_state):
        move = self.moves.pop(0) if self.moves else "c"
        if move == "f":
            return PlayerAction.fold(self.player_id)
        if move == "c":
            return PlayerAction.call(self.player_id)
        return PlayerAction.raise_to(self.player_id, move)


class ScriptedModel(Model):
    """Our profiler, with scripted moves instead of _decide."""

    def __init__(self, moves):
        super().__init__()
        self.moves = list(moves)

    def _decide(self, game_state):
        move = self.moves.pop(0) if self.moves else "c"
        if move == "f":
            return PlayerAction.fold(self.player_id)
        if move == "c":
            return PlayerAction.call(self.player_id)
        return PlayerAction.raise_to(self.player_id, move)


class Sparring(Model):
    """Creates every opportunity: opens the button, bets when checked to,
    calls cheap bets."""

    def _decide(self, gs):
        me = self.player_id
        if gs.can_raise:
            low, high = gs.raise_range
            if gs.street == "preflop" and gs.current_bet == gs.big_blind:
                return PlayerAction.raise_to(me, min(high, max(low, 50)))
            if gs.street != "preflop" and gs.call_amount == 0:
                return PlayerAction.raise_to(
                    me, min(high, max(low, gs.pot // 2))
                )
        if gs.call_amount == 0 or gs.pot_odds < 0.34:
            return PlayerAction.call(me)
        return PlayerAction.fold(me)


def deck(seed):
    cards = full_deck()
    random.Random(seed).shuffle(cards)
    return cards


def scripted_checks():
    teams = ["us", "opp"]
    # Hand 1: opp on the button (seat 1) opens to 60, we (BB) fold.
    me = ScriptedModel(["f"])
    r = play_hand([me, Script([60])], deck(1), [500, 500], button=1,
                  teams=teams)
    assert not r.faults, r.faults
    c = me.profiles["opp"]
    assert c == {"hands": 1, "pf_hands": 1, "steal_opp": 1, "steal": 1,
                 "vpip": 1, "pfr": 1}, c

    # Hand 2: we on the button (seat 0) open to 50, opp (BB) folds.
    me.moves = [50]
    opp = Script(["f"])
    r = play_hand([me, opp], deck(2), [500, 500], button=0, teams=teams)
    assert not r.faults, r.faults
    c = me.profiles["opp"]
    assert c["faced_steal"] == 1 and c["fold_steal"] == 1, c
    assert c["three_bet_opp"] == 1 and c.get("three_bet", 0) == 0, c
    assert c["pf_hands"] == 2 and c["vpip"] == 1, c

    # Hand 3: opp limps the button, we check; flop: we bet 40, opp calls;
    # turn: we bet 80, opp raises to 240, we fold.
    me.moves = ["c", 40, 80, "f"]
    opp = Script(["c", "c", 240])
    r = play_hand([me, opp], deck(3), [500, 500], button=1, teams=teams)
    assert not r.faults, r.faults
    c = me.profiles["opp"]
    assert c["steal_opp"] == 2 and c["steal"] == 1, c  # limp is no steal
    assert c["vpip"] == 2 and c["pfr"] == 1, c  # the limp is voluntary
    assert c["saw_flop"] == 1 and c.get("showdown", 0) == 0, c
    assert c["faced_bet"] == 2 and c.get("fold_bet", 0) == 0, c
    assert c["post_acts"] == 2 and c["post_aggr"] == 1, c

    # Hand 4: we (BB) check a limp... opp checks it down: showdown.
    me.moves = ["c"] * 4
    opp = Script(["c"] * 4)
    r = play_hand([me, opp], deck(4), [500, 500], button=1, teams=teams)
    c = me.profiles["opp"]
    assert c["saw_flop"] == 2 and c["showdown"] == 1, c
    assert c["hands"] == 4 and me.hands_seen == 4, c
    # We never profile ourselves.
    assert "us" not in me.profiles
    print("scripted checks: ok")


def profile_dummies(hands=400):
    for name, cls in DUMMIES.items():
        me = Sparring()
        bot = cls(seed=7)
        teams = ["us", name]
        faults = 0
        for h in range(hands):
            button = h % 2
            r = play_hand([me, bot], deck(1000 + h), [500, 500],
                          button=button, teams=teams)
            faults += 0 in r.faults
        p = me.opponent_profile(name)
        shown = " ".join(
            f"{k}={p[k]:.2f}" for k in
            ("vpip", "pfr", "steal", "fold_to_steal", "three_bet",
             "fold_to_bet", "aggression", "wtsd")
        )
        print(f"{name:7s} {p['label']:16s} {shown}  faults={faults}")


if __name__ == "__main__":
    scripted_checks()
    profile_dummies(int(sys.argv[1]) if len(sys.argv) > 1 else 400)
