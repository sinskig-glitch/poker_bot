"""Checks hand_eval.score orders hands exactly like card_utils.evaluate
(not part of the submission):  .venv/bin/python check_hand_eval.py"""

import random
import time

from card_utils import evaluate, full_deck
from hand_eval import card_int, category, score

rng = random.Random(0)
deck = full_deck()
hands = []
for i in range(20000):
    cards = rng.sample(deck, 5 + i % 3)
    hands.append((evaluate(cards), score([card_int(c) for c in cards])))
# Same category, and the same order on every pair of neighbours once sorted
# by the reference rank (catches any tie-break mismatch).
for ref, fast in hands:
    assert ref[0] == category(fast), (ref, fast)
hands.sort()
for (r1, f1), (r2, f2) in zip(hands, hands[1:]):
    assert (r1 < r2) == (f1 < f2) and (r1 == r2) == (f1 == f2), (r1, r2)
print("order matches evaluate on", len(hands), "hands")

ints = [[card_int(c) for c in rng.sample(deck, 7)] for _ in range(20000)]
t = time.perf_counter()
for h in ints:
    score(h)
fast = (time.perf_counter() - t) / len(ints)
objs = [rng.sample(deck, 7) for _ in range(2000)]
t = time.perf_counter()
for h in objs:
    evaluate(h)
slow = (time.perf_counter() - t) / len(objs)
print(f"score: {fast * 1e6:.1f} us/hand, evaluate: {slow * 1e6:.1f} us/hand")
