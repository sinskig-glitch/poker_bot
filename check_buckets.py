"""Checks buckets.bucket on hand-made spots and times it (not part of the
submission):  .venv/bin/python check_buckets.py"""

import random
import time

from buckets import bucket, name
from card_utils import Card
from hand_eval import card_int


def b(hole, board):
    to = lambda s: [card_int(Card.parse(x)) for x in s.split()]
    return name(*bucket(to(hole), to(board)))


CASES = [
    ("AH KD", "KC 7S 2H", "top_pair_top_kicker@rainbow"),
    ("KH QD", "KC 7S 2H", "top_pair_good_kicker@rainbow"),
    ("KH 5D", "KC 7S 2H", "top_pair_weak_kicker@rainbow"),
    ("AH KD", "AC 7S 2H", "top_pair_top_kicker@rainbow"),
    ("QH QD", "JC 7S 2D", "overpair@rainbow"),
    ("9H 9D", "JC 7S 2D", "middle_pair@rainbow"),
    ("4H 4D", "JC 7S 5D", "bottom_pair@rainbow"),
    ("7H 7D", "JC 7S 2D", "set@rainbow"),
    ("JH 7D", "JC 7S 2D", "two_pair@rainbow"),
    ("JH 7D", "JC 7S 7C", "monster@two_tone_paired"),
    ("JH TD", "JC 7S 7C", "top_pair_good_kicker@two_tone_paired"),
    ("JH 9D", "JC 7S 7C", "top_pair_weak_kicker@two_tone_paired"),
    ("7H 5D", "JC 7S 7C", "trips@two_tone_paired"),
    ("AH 5H", "KH 7H 2C", "ace_high+nut_flush_draw@two_tone"),
    ("QH 5H", "KH 7H 2C", "trash+flush_draw@two_tone"),
    ("9H 8H", "7C 6D 2S", "overcards+oesd@rainbow"),
    ("9H 8H", "7H 6H 2S", "overcards+combo_draw@two_tone"),
    ("9H 5D", "7C 6D 2S", "trash+gutshot@rainbow"),
    ("AD 2C", "3H 4S 9C", "ace_high+gutshot@rainbow"),  # only a 5 makes it
    ("6D 5C", "3H 4S 9C", "trash+oesd@rainbow"),  # 2 or 7
    ("AH QH", "KH 7H 2H", "nut_flush@flushy"),
    ("JH 3H", "KH 7H 2H", "flush@flushy"),
    ("AS KD", "QC JH TD", "straight@rainbow"),
    ("AS KD", "7C 5H 2D", "ace_high@rainbow"),
    ("QS JD", "7C 5H 2D", "overcards@rainbow"),
    ("AH AD", "KC KS 5D 5H", "overpair@rainbow_paired"),
    ("3H 2D", "AC KS QD JH TS", "trash@rainbow"),  # plays the board
    ("AH 2D", "AC KS QD JH TS", "trash@rainbow"),  # plays the board
    ("KH 9H", "AH 7H 2H 5C", "nut_flush@flushy"),  # A on board: K is nuts
    ("8S 8D", "AC KS 9D 4H 2S", "bottom_pair@two_tone".replace(
        "two_tone", "rainbow")),
]
bad = 0
for hole, board, want in CASES:
    got = b(hole, board)
    if got != want:
        bad += 1
        print(f"MISMATCH {hole} | {board}: got {got}, want {want}")
print(f"{len(CASES) - bad}/{len(CASES)} spots as expected")

rng = random.Random(0)
deals = []
for i in range(20000):
    cards = rng.sample(range(52), 2 + 3 + i % 3)
    deals.append((cards[:2], cards[2:]))
t = time.perf_counter()
for hole, board in deals:
    bucket(hole, board)
print(f"bucket: {(time.perf_counter() - t) / len(deals) * 1e6:.1f} us/call")
