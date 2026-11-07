"""
Offline: builds preflop_data.py, the bot's static preflop tables.

    .venv/bin/python build_preflop.py [samples_per_matchup]

Not part of the submission (it uses multiprocessing, which the organisers'
review flags; the bot only imports the generated preflop_data.py).

1. EQUITY: all-in equity of each of the 169 hand classes against each other,
   by Monte Carlo over concrete combos and boards (hand_eval.score).
2. Heads-up push/fold Nash equilibrium for stacks of 1..NASH_MAX_BB big
   blinds (fictitious play on EQUITY): the deepest stack at which the small
   blind shoves each hand, and the big blind calls a shove with it.
3. The button open range: the strongest OPEN_PERCENT% of combos by equity
   against a random hand. Never a limp: every other hand folds.
"""

import random
import sys
from multiprocessing import Pool

from hand_eval import RANK_CHARS, score

OPEN_PERCENT = 85
NASH_MAX_BB = 20
FP_ITERATIONS = 400


def hand_classes():
    """The 169 classes, strongest-looking first: (label, kind, hi, lo)."""
    out = []
    for hi in range(12, -1, -1):
        out.append((RANK_CHARS[hi] * 2, "pair", hi, hi))
        for lo in range(hi - 1, -1, -1):
            name = RANK_CHARS[hi] + RANK_CHARS[lo]
            out.append((name + "s", "suited", hi, lo))
            out.append((name + "o", "offsuit", hi, lo))
    return out


CLASSES = hand_classes()
COMBOS = [{"pair": 6, "suited": 4, "offsuit": 12}[k] for _, k, _, _ in CLASSES]


def sample_combo(rng, cls):
    _, kind, hi, lo = cls
    if kind == "suited":
        s = rng.randrange(4)
        return (hi << 2) | s, (lo << 2) | s
    s1 = rng.randrange(4)
    s2 = rng.randrange(3)
    if s2 >= s1:
        s2 += 1
    return (hi << 2) | s1, (lo << 2) | s2


def matchup(args):
    """Equity of class i against class j over `samples` deals."""
    i, j, samples, seed = args
    rng = random.Random(seed)
    a_cls, b_cls = CLASSES[i], CLASSES[j]
    total = 0.0
    done = 0
    attempts = 0
    while done < samples and attempts < samples * 50:
        attempts += 1
        a = sample_combo(rng, a_cls)
        b = sample_combo(rng, b_cls)
        if a[0] in b or a[1] in b:
            continue
        dead = {a[0], a[1], b[0], b[1]}
        rest = [c for c in range(52) if c not in dead]
        board = rng.sample(rest, 5)
        sa = score([a[0], a[1]] + board)
        sb = score([b[0], b[1]] + board)
        total += 1.0 if sa > sb else 0.5 if sa == sb else 0.0
        done += 1
    return i, j, total / done if done else 0.5


def equity_matrix(samples):
    n = len(CLASSES)
    jobs = [(i, j, samples, i * 1000 + j) for i in range(n)
            for j in range(i, n)]
    eq = [[0.5] * n for _ in range(n)]
    with Pool() as pool:
        for i, j, e in pool.imap_unordered(matchup, jobs, chunksize=64):
            eq[i][j] = e
            eq[j][i] = 1.0 - e
    for i in range(n):
        eq[i][i] = 0.5  # same class: symmetric by definition
    return eq


def nash(args):
    """Fictitious play for heads-up push/fold with stack d big blinds.

    SB folds (-0.5) or shoves; BB folds (-1) or calls. Returns the average
    shove and call frequency per class.
    """
    d, eq = args
    n = len(CLASSES)
    w = COMBOS
    push = [1.0] * n
    call = [0.5] * n
    for it in range(1, FP_ITERATIONS + 1):
        # BB's best response to the SB's average shove range.
        pw = [w[i] * push[i] for i in range(n)]
        mass = sum(pw) or 1.0
        br_call = []
        for j in range(n):
            row = eq[j]
            e = sum(pw[i] * row[i] for i in range(n)) / mass
            br_call.append(1.0 if e * 2 * d - d > -1.0 else 0.0)
        # SB's best response to the BB's average call range.
        cw = [w[j] * call[j] for j in range(n)]
        fold_mass = sum(w[j] - cw[j] for j in range(n))
        total = sum(w)
        br_push = []
        for i in range(n):
            row = eq[i]
            called = sum(cw[j] * (row[j] * 2 * d - d) for j in range(n))
            ev = (fold_mass * 1.0 + called) / total
            br_push.append(1.0 if ev > -0.5 else 0.0)
        step = 1.0 / (it + 1)
        push = [p + (b - p) * step for p, b in zip(push, br_push)]
        call = [c + (b - c) * step for c, b in zip(call, br_call)]
    return d, push, call


def main():
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    n = len(CLASSES)
    print(f"equity matrix: {n * (n + 1) // 2} matchups x {samples} deals")
    eq = equity_matrix(samples)

    print(f"push/fold Nash for 1..{NASH_MAX_BB} bb")
    push_max = [0] * n
    call_max = [0] * n
    with Pool() as pool:
        for d, push, call in pool.imap_unordered(
            nash, [(d, eq) for d in range(1, NASH_MAX_BB + 1)]
        ):
            for i in range(n):
                if push[i] >= 0.5:
                    push_max[i] = max(push_max[i], d)
                if call[i] >= 0.5:
                    call_max[i] = max(call_max[i], d)

    total = sum(COMBOS)
    vs_random = [sum(COMBOS[j] * eq[i][j] for j in range(n)) / total
                 for i in range(n)]
    order = sorted(range(n), key=lambda i: -vs_random[i])
    opened = set()
    combos = 0
    for i in order:
        if combos >= OPEN_PERCENT / 100 * total:
            break
        opened.add(i)
        combos += COMBOS[i]
    folded = [CLASSES[i][0] for i in order if i not in opened]
    print(f"open {100 * combos / total:.1f}% of combos; fold {folded}")

    lines = [
        "# Generated by build_preflop.py: do not edit by hand.",
        f"# {samples} Monte Carlo deals per matchup.",
        "",
        "# The 169 starting-hand classes.",
        f"HANDS = {[c[0] for c in CLASSES]!r}",
        "",
        "# Combos per class (pair 6, suited 4, offsuit 12; 1326 in all).",
        f"COMBOS = {COMBOS!r}",
        "",
        f"OPEN_PERCENT = {OPEN_PERCENT}",
        f"NASH_MAX_BB = {NASH_MAX_BB}",
        "",
        "# Static chart, hand -> (open_raise, push_max_bb, call_max_bb):",
        "#   open_raise   1 if the button open-raises it (no limps, ever)",
        "#   push_max_bb  heads-up Nash: the SB shoves it with <= this many bb",
        "#   call_max_bb  heads-up Nash: the BB calls a shove with <= this",
        "PREFLOP_CHART = {",
    ]
    for i, (label, _, _, _) in enumerate(CLASSES):
        lines.append(
            f"    {label!r}: ({int(i in opened)}, {push_max[i]}, "
            f"{call_max[i]}),"
        )
    lines += [
        "}",
        "",
        "# EQUITY[i][j]: all-in equity of HANDS[i] against HANDS[j], per mille.",
        "EQUITY = [",
    ]
    for i in range(n):
        lines.append("    [" + ",".join(str(round(1000 * e))
                                         for e in eq[i]) + "],")
    lines += ["]", ""]
    with open("preflop_data.py", "w") as f:
        f.write("\n".join(lines))
    print("wrote preflop_data.py")


if __name__ == "__main__":
    main()
