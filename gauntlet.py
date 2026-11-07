"""
Gauntlet: does a change to model.py help without hurting anywhere else?

    .venv/bin/python gauntlet.py                    # every opponent
    .venv/bin/python gauntlet.py --set tune         # only the tuning set
    .venv/bin/python gauntlet.py --deals 2000 --times 2

Plays model.py ("new") and the frozen baseline-v1 copy ("old",
sparring_baseline.py) against the same opponents on the same decks, then
prints both scores and the difference new - old with a 95% interval. Both
play the same cards, so the difference is far less noisy than either
score. Also plays new vs old head-to-head.

Opponents are in two sets. Tune on "tune". Look at "holdout" only to check
a finished change: if it helps on tune but not on holdout, it was tuned to
the opponents, not to poker.

Not part of the submission.
"""

import argparse
import math
import os
import pickle
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

import sparring
from arena.match import MatchConfig, repeat_match
from arena.players import player
from sparring_example import Model as ExampleBot


def _opponents():
    """name -> (set, a bot object to pickle, or a dummy name)."""
    S = sparring
    out = {}
    for name in ("call", "random", "shove", "tight", "equity"):
        out[name] = ("tune", name)
    out["example"] = ("tune", ExampleBot())
    out["station"] = ("tune", S.StyleBot(1, **S.STATION))
    out["maniac"] = ("tune", S.StyleBot(2, **S.MANIAC))
    out["nit"] = ("tune", S.StyleBot(3, **S.NIT))
    for seed in range(4):
        out[f"style{seed}"] = ("tune", S.random_style(seed))
    out["trapper"] = ("holdout", S.StyleBot(4, **S.TRAPPER))
    out["shifter"] = ("holdout", S.ShifterBot(5))
    out["counter"] = ("holdout", S.CounterBot(6))
    for seed in range(100, 104):
        out[f"style{seed}"] = ("holdout", S.random_style(seed))
    return out


def _spec(folder, name, bot):
    """A player spec: a dummy name, or a pickle written to folder."""
    if isinstance(bot, str):
        return bot
    path = os.path.join(folder, name + ".pkl")
    with open(path, "wb") as f:
        pickle.dump(bot, f)
    return path


def _play(us_spec, opp_spec, deals, times, seed):
    """Our net chips per (match, deal), both seat rotations summed."""
    config = MatchConfig(deals=deals, seed=seed)
    logs = repeat_match([player(us_spec), player(opp_spec)], config, times)
    us = player(us_spec).name
    net, faults = {}, 0
    for m, log in enumerate(logs):
        for h in log.hands:
            seat = h.seats.index(us)
            key = (m, h.deal)
            net[key] = net.get(key, 0) + h.net[seat]
            faults += seat in h.faults
    return net, faults


def _bb100(values, hands_per_value, bb=20):
    """Mean and 95% interval, in big blinds per 100 hands."""
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / max(1, n - 1)
    scale = 100.0 / bb / hands_per_value
    return mean * scale, 1.96 * math.sqrt(var / n) * scale


def main():
    parser = argparse.ArgumentParser(prog="gauntlet.py")
    parser.add_argument("--set", choices=("tune", "holdout", "all"),
                        default="all")
    parser.add_argument("--deals", type=int, default=1000)
    parser.add_argument("--times", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=max(1, os.cpu_count() - 2))
    args = parser.parse_args()

    import model
    import sparring_baseline
    opponents = {n: v for n, v in _opponents().items()
                 if args.set == "all" or v[0] == args.set}
    started = time.time()
    with tempfile.TemporaryDirectory() as folder:
        new = _spec(folder, "new", model.Model())
        old = _spec(folder, "old", sparring_baseline.Model())
        specs = {n: _spec(folder, n, bot) for n, (_, bot) in opponents.items()}
        jobs = {}
        with ProcessPoolExecutor(args.jobs) as pool:
            for n, spec in specs.items():
                for who, us in (("new", new), ("old", old)):
                    jobs[(n, who)] = pool.submit(
                        _play, us, spec, args.deals, args.times, args.seed)
            jobs[("old (head-to-head)", "new")] = pool.submit(
                _play, new, old, args.deals, args.times, args.seed)
            results = {k: f.result() for k, f in jobs.items()}

    print(f"{args.deals} deals x 2 seats x {args.times}: "
          f"{2 * args.deals * args.times} hands per opponent, "
          f"{time.time() - started:.0f}s\n")
    print(f"{'opponent':<20} {'set':<8} {'old bb/100':>10} {'new bb/100':>10}"
          f" {'new - old':>16}  verdict")
    deltas = {"tune": [], "holdout": []}
    for n, (group, _) in opponents.items():
        new_net, new_faults = results[(n, "new")]
        old_net, _ = results[(n, "old")]
        old_bb, _ = _bb100(list(old_net.values()), 2)
        new_bb, _ = _bb100(list(new_net.values()), 2)
        diff = [new_net[k] - old_net[k] for k in new_net]
        d, ci = _bb100(diff, 2)
        verdict = ("better" if d - ci > 0 else "WORSE" if d + ci < 0
                   else "same")
        if new_faults:
            verdict += f"  {new_faults} FAULTS"
        deltas[group].append(d)
        print(f"{n:<20} {group:<8} {old_bb:>+10.1f} {new_bb:>+10.1f} "
              f"{d:>+8.1f} ± {ci:<5.1f}  {verdict}")
    h2h, _ = results[("old (head-to-head)", "new")]
    d, ci = _bb100(list(h2h.values()), 2)
    verdict = "better" if d - ci > 0 else "WORSE" if d + ci < 0 else "same"
    print(f"{'new vs old':<20} {'holdout':<8} {'':>10} {d:>+10.1f} "
          f"{'':>16}  {verdict} (± {ci:.1f})")
    print()
    for group, ds in deltas.items():
        if ds:
            print(f"average new - old on {group}: {sum(ds) / len(ds):+.1f}"
                  f" bb/100 over {len(ds)} opponents")


if __name__ == "__main__":
    main()
