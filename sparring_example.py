"""Sparring partner: the example bot from CLAUDE.md. Not part of the submission."""
from card_utils import evaluate
from player_action import PlayerAction


class Model:
    def __init__(self):
        self.hand = []
        self.player_id = None

    def seed(self, hand, player_id):
        self.hand = hand
        self.player_id = player_id

    def run(self, actions, game_state):
        me = self.player_id
        if len(game_state.board) >= 3:
            strong = evaluate(self.hand + list(game_state.board))[0] >= 2
        else:
            high, low = sorted(card.value for card in self.hand)[::-1]
            strong = high == low or low >= 10
        if strong and "raise" in game_state.legal_actions:
            low, high = game_state.raise_range
            return PlayerAction.raise_to(me, min(high, max(low, game_state.pot)))
        if game_state.call_amount == 0 or game_state.pot_odds < 0.25:
            return PlayerAction.call(me)
        return PlayerAction.fold(me)
