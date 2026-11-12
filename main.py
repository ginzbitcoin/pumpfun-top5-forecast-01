"""pumpfun-top5-forecast-01: Monte Carlo forecast of the top 5 new coins.

Python 3 standard library only. No network and no model calls. One seeded
forecast is written and later scored at every answer read in task.json.

Each known coin's log10 market cap (SOL) diffuses from its last mark.
Drift is that coin's last per-step log growth, shrunk 50% toward the median
growth of pool coins, and it applies only for the first 12 steps. Volatility
is 0.15 per step for pool coins and 0.30 for bonding-curve coins, and it
stops accumulating after 18 steps. Curve coins mean-revert toward the ~28 SOL
floor. Phantom newcomers (about 2 per step, at most 40 per read) are born
uniformly over the horizon. Their opening cap is drawn from the first-seen
caps of top-5 entrants in the second half of the history. They cannot be
named, so their place share stays in the unnamed mass. Each place's size
distribution leaves 5% of its mass unnamed. The horizon is the gap from the
last mark to each read in task.json, in 10-minute steps.
"""
import json
import math
import os
import random
import sys
from datetime import datetime

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

SEED = 20261112
N_SIMS = 6000
MAX_CANDIDATES = 400
ARRIVAL_RATE_PER_STEP = 2.0
MAX_PHANTOMS = 40
DRIFT_STEPS = 12
VOL_CAP_STEPS = 18
SIGMA_POOL = 0.15
SIGMA_CURVE = 0.30
SIGMA_PHANTOM = 0.30
CURVE_FLOOR_LOG = math.log10(28.0)
P_MIN_NAME = 0.004
SIZE_UNNAMED = 0.05

# Set from task.json before the simulation reads it.
EDGES = []


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_history(path):
    marks = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                marks.append(json.loads(line))
    return [mark for mark in marks if mark.get("ok") and isinstance(mark.get("rows"), list)]


def bin_of(log_cap, edges):
    lo, hi = 0, len(edges)
    while lo < hi:
        mid = (lo + hi) >> 1
        if edges[mid] <= log_cap:
            lo = mid + 1
        else:
            hi = mid
    return lo


def median_pool_growth(series):
    growths = []
    for obs in series.values():
        for left, right in zip(obs, obs[1:]):
            i0, x0, _v0, _c0 = left
            i1, x1, v1, _c1 = right
            if i1 == i0 + 1 and v1 == "pool":
                growths.append((x1 - x0) / (i1 - i0))
    if not growths:
        return 0.05
    growths.sort()
    return min(max(growths[len(growths) // 2], 0.0), 0.12)


def arrival_log_caps(series, first_rank, n_marks):
    """First-seen log caps of coins that entered the top 5.

    Prefer entrants from the second half of the history. The opening marks
    are thin, and later top-5 newcomers appear already near 1,000-3,000 SOL.
    """
    half = max(1, n_marks // 2)
    caps = [
        obs[0][1]
        for mint, obs in series.items()
        if first_rank.get(mint, 999) <= 5 and obs[0][0] >= half
    ]
    if len(caps) < 5:
        caps = [
            obs[0][1]
            for mint, obs in series.items()
            if first_rank.get(mint, 999) <= 5
        ]
    if len(caps) < 5:
        caps = [
            obs[0][1]
            for mint, obs in series.items()
            if first_rank.get(mint, 999) <= 20
        ]
    if len(caps) < 5:
        caps = [math.log10(1500.0)]
    caps.sort()
    return caps


def coin_dynamics(obs, med_growth):
    _i, _x, venue, _created = obs[-1]
    growth = None
    if len(obs) >= 2 and obs[-1][0] == obs[-2][0] + 1:
        growth = (obs[-1][1] - obs[-2][1]) / (obs[-1][0] - obs[-2][0])
    if venue == "pool":
        raw = med_growth if growth is None else 0.5 * growth + 0.5 * med_growth
        return min(max(raw, -0.15), 0.25), SIGMA_POOL
    raw = 0.0 if growth is None else min(max(0.5 * growth, -0.3), 0.1)
    return raw, SIGMA_CURVE


def diffuse_known(rng, last, drift, sigma, steps):
    _i, log_cap, venue, _created = last
    mu = log_cap + drift * min(steps, DRIFT_STEPS)
    if venue != "pool":
        weight = 1.0 - math.exp(-steps / 3.0)
        mu = (1.0 - weight) * mu + weight * CURVE_FLOOR_LOG
    sd = sigma * math.sqrt(min(steps, VOL_CAP_STEPS))
    return rng.gauss(mu, sd)


def diffuse_phantom(rng, steps, arrival_caps, med_growth):
    age = rng.random() * steps
    base = arrival_caps[rng.randrange(len(arrival_caps))]
    mu = base + med_growth * min(age, DRIFT_STEPS)
    sd = SIGMA_PHANTOM * math.sqrt(min(max(age, 1.0), VOL_CAP_STEPS))
    return rng.gauss(mu, sd)


def simulate(rng, horizons, candidates, last_obs, drift, sigma, arrival_caps, med_growth, places):
    place_counts = [dict() for _ in range(places)]
    phantom_place = [0] * places
    size_counts = [dict() for _ in range(places)]
    phantom_draws = 0
    for steps in horizons:
        n_phantoms = min(MAX_PHANTOMS, max(0, int(round(ARRIVAL_RATE_PER_STEP * steps))))
        phantom_draws += n_phantoms
        for _sim in range(N_SIMS):
            drawn = []
            for mint in candidates:
                log_cap = diffuse_known(
                    rng, last_obs[mint], drift[mint], sigma[mint], steps
                )
                drawn.append((log_cap, mint))
            for _phantom in range(n_phantoms):
                drawn.append(
                    (diffuse_phantom(rng, steps, arrival_caps, med_growth), None)
                )
            drawn.sort(key=lambda item: -item[0])
            for place in range(places):
                log_cap, mint = drawn[place]
                if mint is None:
                    phantom_place[place] += 1
                else:
                    place_counts[place][mint] = place_counts[place].get(mint, 0) + 1
                size_bin = bin_of(log_cap, EDGES)
                size_counts[place][size_bin] = size_counts[place].get(size_bin, 0) + 1
    return place_counts, phantom_place, size_counts, phantom_draws


def build_forecast(place_counts, size_counts, total_sims, ranked, places):
    probabilities = []
    for place in range(places):
        named = 0
        rows = sorted(place_counts[place].items(), key=lambda item: -item[1])
        for mint, count in rows:
            share = count / total_sims
            if share < P_MIN_NAME or named >= 100:
                break
            probabilities.append(
                {"mint": mint, "place": place + 1, "p": round(share, 6)}
            )
            named += 1

    top5 = []
    for place in range(places):
        rows = sorted(place_counts[place].items(), key=lambda item: -item[1])
        for mint, _count in rows:
            if mint not in top5:
                top5.append(mint)
                break
    if len(top5) < places:
        for mint in ranked:
            if mint not in top5:
                top5.append(mint)
            if len(top5) == places:
                break

    sizes = []
    kept = 1.0 - SIZE_UNNAMED
    for place in range(places):
        for size_bin, count in sorted(size_counts[place].items()):
            share = (count / total_sims) * kept
            if share < 0.0005:
                continue
            sizes.append(
                {"place": place + 1, "bin": size_bin, "p": round(share, 6)}
            )

    return {
        "probabilities": probabilities,
        "top5": top5[:places],
        "sizes": sizes,
    }


def main():
    global EDGES
    with open(os.path.join(INPUT_DIR, "task.json"), "r", encoding="utf-8") as handle:
        task = json.load(handle)
    marks = load_history(os.path.join(INPUT_DIR, "history.ndjson"))
    if not marks:
        raise SystemExit("the history holds no ok mark")

    EDGES = task["size"]["edges"]
    places = task["places"]
    last_at = parse_time(marks[-1]["at"])
    horizons = [
        max(1, int(round((parse_time(read) - last_at).total_seconds() / 600.0)))
        for read in task["reads"]
    ]

    series = {}
    first_rank = {}
    for index, mark in enumerate(marks):
        for row in mark["rows"]:
            mint = row["mint"]
            log_cap = math.log10(int(row["market_cap_lamports"]) / 1e9)
            series.setdefault(mint, []).append(
                (index, log_cap, row["venue"], row["created_at"])
            )
            if mint not in first_rank:
                first_rank[mint] = row["rank"]

    med_growth = median_pool_growth(series)
    arrival_caps = arrival_log_caps(series, first_rank, len(marks))
    last_obs = {mint: obs[-1] for mint, obs in series.items()}
    ranked = sorted(series, key=lambda mint: -last_obs[mint][1])
    candidates = ranked[:MAX_CANDIDATES]

    drift = {}
    sigma = {}
    for mint in candidates:
        drift[mint], sigma[mint] = coin_dynamics(series[mint], med_growth)

    rng = random.Random(SEED)
    place_counts, phantom_place, size_counts, phantom_draws = simulate(
        rng,
        horizons,
        candidates,
        last_obs,
        drift,
        sigma,
        arrival_caps,
        med_growth,
        places,
    )
    total_sims = N_SIMS * len(horizons)
    forecast = build_forecast(place_counts, size_counts, total_sims, ranked, places)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, task["output"])
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(forecast) + "\n")

    print(
        "marks=%d candidates=%d med_pool_growth=%.3f horizon_steps=%s "
        "phantoms/read~%d phantom_place_share=%s wrote=%s"
        % (
            len(marks),
            len(candidates),
            med_growth,
            horizons,
            phantom_draws // max(1, len(horizons)),
            [round(phantom_place[k] / total_sims, 3) for k in range(places)],
            out_path,
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
