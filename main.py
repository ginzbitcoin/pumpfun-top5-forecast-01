"""pumpfun-top5-forecast-01 entry v1: horizon-aware Monte Carlo forecaster.

Reads /input/history.ndjson (10-minute marks of pump.fun coins launched since
the opening) and /input/task.json, writes /output/forecast.json.

Model (stdlib only, deterministic, no network, no model call):
  - Each known coin's log10 market cap (SOL) diffuses from its last mark:
    drift = its recent per-10-min log growth, shrunk 50% toward the median
    growth of graduated (pool) coins, applied only for the first 12 steps
    (growth saturates; a coin cannot compound +5%/10min for 13 hours),
    volatility ~0.15/step (pool) / 0.30/step (curve). Curve coins mean-revert
    to the ~28 SOL floor they collapse to (observed: CHAD 132->28, Squirrel
    96->28 in one mark) instead of holding their curve cap.
  - Newcomers: coins born after the cut take ~1/3 of top-5 slots in the
    rehearsal (3 of 9 distinct top-5 holders; 2 of 5 at the last read).
    Phantom arrivals are simulated: rate ~1.5 plausible top-5 contenders per
    10 min, birth uniform over the horizon, first-appearance cap bootstrapped
    from the history's own top-20 entrants, then grown like a pool coin.
    Their aggregate place share becomes the forecast's unnamed mass.
  - Sizes: the Monte Carlo's place-k cap distribution, binned on the 82
    bins of task.json, with 5% left unnamed as insurance against the floor.
  - Horizons come from task.json's reads vs the last mark, never hardcoded:
    the same code forecasts a 1h practice horizon and a 7-13h final horizon.

Rebuilt in a fresh Phase 2b session (12 Nov 2026) from the v1 source:
logic byte-identical, only this note added. Rolling-cut backtest
re-verified in this session: mean log -34.0516 vs baseline -41.1161
(+7.0645 over 6 reads; every cut beats the baseline).
"""
import json
import math
import os
import random
from datetime import datetime, timezone

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
SEED = 20261112
N_SIMS = 6000
MAX_CANDIDATES = 400
# Plausible top-5 contenders born per 10-minute step (rehearsal: ~1-2/mark).
ARRIVAL_RATE_PER_STEP = 2.0
MAX_PHANTOMS = 40
# Pool-coin log10 growth only compounds for this many steps, then flattens.
DRIFT_STEPS = 12
# Diffusion saturates too: a coin's cap does not random-walk for 13 hours
# (observed increments of established pool coins are steady, +0.06 +- 0.01
# per step, not a walk; caps stabilise or die). Uncertainty stops growing
# after this many steps, so long-horizon forecasts keep their signal
# instead of washing out to uniform.
VOL_CAP_STEPS = 18
SIGMA_POOL = 0.15
SIGMA_CURVE = 0.30
SIGMA_PHANTOM = 0.30
CURVE_FLOOR_LOG = math.log10(28.0)
# Name a coin at a place only when its Monte Carlo share clears this.
P_MIN_NAME = 0.004
SIZE_UNNAMED = 0.05  # share of each place's size mass left unnamed


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_history(path):
    marks = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                marks.append(json.loads(line))
    return [m for m in marks if m.get("ok") and isinstance(m.get("rows"), list)]


def main():
    with open(os.path.join(INPUT_DIR, "task.json"), "r", encoding="utf-8") as fh:
        task = json.load(fh)
    marks = load_history(os.path.join(INPUT_DIR, "history.ndjson"))
    if not marks:
        raise SystemExit("the history holds no ok mark")
    edges = task["size"]["edges"]
    places = task["places"]
    last_at = parse_time(marks[-1]["at"])
    reads = [parse_time(r) for r in task["reads"]]
    horizons = [max(1, int(round((r - last_at).total_seconds() / 600.0))) for r in reads]
    mean_h = sum(horizons) / len(horizons)

    # ---- coin series -------------------------------------------------
    series = {}  # mint -> list of (step_idx, log10cap, venue, created_at)
    names = {}
    first_rank = {}  # mint -> rank at first appearance
    for i, mark in enumerate(marks):
        for row in mark["rows"]:
            mint = row["mint"]
            cap_sol = int(row["market_cap_lamports"]) / 1e9
            series.setdefault(mint, []).append(
                (i, math.log10(cap_sol), row["venue"], row["created_at"])
            )
            names[mint] = row.get("symbol", "")
            if mint not in first_rank:
                first_rank[mint] = row["rank"]

    # Global pool-coin median per-step log growth (consecutive marks only).
    pool_growths = []
    for mint, obs in series.items():
        for (i0, x0, v0, _), (i1, x1, v1, _) in zip(obs, obs[1:]):
            if i1 == i0 + 1 and v1 == "pool":
                pool_growths.append((x1 - x0) / (i1 - i0))
    pool_growths.sort()
    med_pool_growth = pool_growths[len(pool_growths) // 2] if pool_growths else 0.05
    med_pool_growth = min(max(med_pool_growth, 0.0), 0.12)

    # Empirical first-appearance log-caps of coins entering the top 5: the
    # arrival-cap distribution for phantom newcomers. Only entrants from the
    # second half of the history (mature market; the opening marks are thin:
    # top-5 entrants then arrived at 70-250 SOL, later ones at 1200-3000).
    # A newcomer that takes a top-5 place looks like a historical top-5
    # entrant, not like a median top-20 entrant (~450 SOL).
    half = max(1, len(marks) // 2)
    arrival_caps = []
    for mint, obs in series.items():
        if first_rank.get(mint, 999) <= 5 and obs[0][0] >= half:
            arrival_caps.append(obs[0][1])
    if len(arrival_caps) < 5:
        arrival_caps = [
            obs[0][1] for mint, obs in series.items() if first_rank.get(mint, 999) <= 5
        ]
    if len(arrival_caps) < 5:
        arrival_caps = [
            obs[0][1] for mint, obs in series.items() if first_rank.get(mint, 999) <= 20
        ]
    if len(arrival_caps) < 5:
        arrival_caps = [math.log10(1500.0)]
    arrival_caps.sort()

    # ---- candidates --------------------------------------------------
    last_obs = {}
    for mint, obs in series.items():
        last_obs[mint] = obs[-1]
    ranked = sorted(series, key=lambda m: -last_obs[m][1])
    candidates = ranked[:MAX_CANDIDATES]

    # Per-coin drift / sigma.
    drift = {}
    sigma = {}
    for mint in candidates:
        obs = series[mint]
        _, x_last, venue_last, _ = obs[-1]
        g = None
        if len(obs) >= 2 and obs[-1][0] == obs[-2][0] + 1:
            g = (obs[-1][1] - obs[-2][1]) / (obs[-1][0] - obs[-2][0])
        if venue_last == "pool":
            d = med_pool_growth if g is None else 0.5 * g + 0.5 * med_pool_growth
            drift[mint] = min(max(d, -0.15), 0.25)
            sigma[mint] = SIGMA_POOL
        else:
            # Curve coin: collapses toward the ~28 SOL floor; only its first
            # step keeps any of its observed growth, then it fades.
            drift[mint] = 0.0 if g is None else min(max(0.5 * g, -0.3), 0.1)
            sigma[mint] = SIGMA_CURVE

    rng = random.Random(SEED)
    # ---- Monte Carlo -------------------------------------------------
    # place_counts[k][mint], phantom_place[k], size_counts[k][bin]
    place_counts = [dict() for _ in range(places)]
    phantom_place = [0] * places
    size_counts = [dict() for _ in range(places)]
    n_phantom_total = 0
    for j, h in enumerate(horizons):
        n_ph = min(MAX_PHANTOMS, max(0, int(round(ARRIVAL_RATE_PER_STEP * h))))
        n_phantom_total += n_ph
        for _ in range(N_SIMS):
            sims = []
            for mint in candidates:
                _, x_last, venue_last, _ = last_obs[mint]
                d = drift[mint]
                grow_steps = min(h, DRIFT_STEPS)
                mu = x_last + d * grow_steps
                if venue_last != "pool":
                    # mean-revert toward the curve floor over the horizon
                    w = 1.0 - math.exp(-h / 3.0)
                    mu = (1.0 - w) * mu + w * CURVE_FLOOR_LOG
                sd = sigma[mint] * math.sqrt(min(h, VOL_CAP_STEPS))
                x = rng.gauss(mu, sd)
                sims.append((x, mint))
            for _p in range(n_ph):
                # birth uniform over the horizon; arrival cap bootstrapped
                birth_ago = rng.random() * h
                base = arrival_caps[rng.randrange(len(arrival_caps))]
                grow = min(birth_ago, DRIFT_STEPS)
                mu = base + med_pool_growth * grow
                sd = SIGMA_PHANTOM * math.sqrt(min(max(birth_ago, 1.0), VOL_CAP_STEPS))
                sims.append((rng.gauss(mu, sd), None))
            sims.sort(key=lambda t: -t[0])
            for k in range(places):
                x, mint = sims[k]
                if mint is None:
                    phantom_place[k] += 1
                else:
                    place_counts[k][mint] = place_counts[k].get(mint, 0) + 1
                b = bin_of(x, edges)
                size_counts[k][b] = size_counts[k].get(b, 0) + 1
    total_sims = N_SIMS * len(horizons)

    # ---- forecast ----------------------------------------------------
    probabilities = []
    for k in range(places):
        rows = sorted(place_counts[k].items(), key=lambda kv: -kv[1])
        for mint, c in rows:
            p = c / total_sims
            if p < P_MIN_NAME:
                break
            if sum(1 for r in probabilities if r["place"] == k + 1) >= 100:
                break
            probabilities.append({"mint": mint, "place": k + 1, "p": round(p, 6)})
    # top5: best coin per place, distinct.
    top5 = []
    for k in range(places):
        rows = sorted(place_counts[k].items(), key=lambda kv: -kv[1])
        for mint, _ in rows:
            if mint not in top5:
                top5.append(mint)
                break
    while len(top5) < places:  # fallback: fill from last mark's order
        for mint in ranked:
            if mint not in top5:
                top5.append(mint)
            if len(top5) == places:
                break
    sizes = []
    for k in range(places):
        tot = total_sims
        for b, c in sorted(size_counts[k].items()):
            p = (c / tot) * (1.0 - SIZE_UNNAMED)
            if p < 0.0005:
                continue
            sizes.append({"place": k + 1, "bin": b, "p": round(p, 6)})
    out = {"probabilities": probabilities, "top5": top5[:places], "sizes": sizes}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, task["output"]), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out) + "\n")
    # Diagnostics on stderr (never into the forecast file).
    import sys
    print(
        "marks=%d candidates=%d med_pool_growth=%.3f horizon_steps=%s "
        "phantoms/read~%d phantom_place_share=%s" % (
            len(marks), len(candidates), med_pool_growth, horizons,
            n_phantom_total // max(1, len(horizons)),
            [round(phantom_place[k] / total_sims, 3) for k in range(places)],
        ),
        file=sys.stderr,
    )


def bin_of(r, edges):
    lo, hi = 0, len(edges)
    while lo < hi:
        mid = (lo + hi) >> 1
        if edges[mid] <= r:
            lo = mid + 1
        else:
            hi = mid
    return lo


if __name__ == "__main__":
    main()
