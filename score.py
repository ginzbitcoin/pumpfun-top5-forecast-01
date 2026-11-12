"""Local scorer: exact replica of the pumpfun-top5-forecast-01 scoring rule
(grader/forecast/ranked.ts + RULES.txt / competition.yaml).

Score a forecast.json against a list of answer reads. Each read:
  {"chart": [mint, ...] (place 1 first, up to 100),
   "caps_sol": [cap place 1..5 in SOL]}
Rows naming a mint no history row names are dropped first (history_mints).
Log score = mean over reads of (order score + size score), each floored at 1e-4.
"""
import json
import math

P_FLOOR = 1e-4
EDGES = [2 + 0.05 * i for i in range(81)]  # 2.00 .. 6.00


def round6(x):
    r = round(x * 1e6) / 1e6
    return 0 if r == 0 else r


def bin_of(r):
    lo, hi = 0, len(EDGES)
    while lo < hi:
        mid = (lo + hi) >> 1
        if EDGES[mid] <= r:
            lo = mid + 1
        else:
            hi = mid
    return lo


def load_forecast(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def score_forecast(fc, reads, history_mints):
    """fc: parsed forecast.json. reads: list of {chart, caps_sol}.
    history_mints: set of mints named by any history row."""
    named = [dict() for _ in range(5)]   # per place: mint -> p
    sums = [0.0] * 5
    for row in fc["probabilities"]:
        mint, place, p = row["mint"], row["place"], row["p"]
        if mint not in history_mints:
            continue  # dropped, p back in the unnamed share
        named[place - 1][mint] = p
        sums[place - 1] += p
    size_named = [dict() for _ in range(5)]  # per place: bin -> p
    size_sums = [0.0] * 5
    for row in fc["sizes"]:
        place, b, p = row["place"], row["bin"], row["p"]
        size_named[place - 1][b] = p
        size_sums[place - 1] += p
    top5 = fc["top5"]

    order_total = 0.0
    size_total = 0.0
    agreement_total = 0
    per_read = []
    for read in reads:
        chart = read["chart"]
        caps = read["caps_sol"]
        n = min(5, len(chart))
        o = 0.0
        for k in range(1, n + 1):
            actual = chart[k - 1]
            at = named[k - 1]
            if actual in at:
                p = at[actual]
            else:
                unnamed = sum(1 for c in chart if c not in at)
                left = max(0.0, 1.0 - sums[k - 1])
                p = 0.0 if unnamed == 0 else left / unnamed
            o += math.log(max(p, P_FLOOR))
        s = 0.0
        for k in range(1, n + 1):
            b = bin_of(math.log10(caps[k - 1]))
            at = size_named[k - 1]
            if b in at:
                p = at[b]
            else:
                unnamed = 82 - len(at)
                left = max(0.0, 1.0 - size_sums[k - 1])
                p = 0.0 if unnamed == 0 else left / unnamed
            s += math.log(max(p, P_FLOOR))
        ag = 0
        head = chart[:5]
        for i, mint in enumerate(top5):
            if mint in head:
                ag += 5 - abs(i - head.index(mint))
        order_total += o
        size_total += s
        agreement_total += ag
        per_read.append((round6(o), round6(s), round6(o + s), ag))
    m = len(reads)
    return {
        "log_score": round6((order_total + size_total) / m),
        "order_score": round6(order_total / m),
        "size_score": round6(size_total / m),
        "agreement": agreement_total,
        "per_read": per_read,
    }


def history_mints_from(path):
    mints = set()
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            mark = json.loads(line)
            for row in mark.get("rows") or []:
                mints.add(row["mint"])
    return mints


def reads_from_marks(marks):
    """Turn history marks into pseudo-answer reads (chart = top 100 rows)."""
    out = []
    for mark in marks:
        rows = mark.get("rows") or []
        if len(rows) < 5:
            continue
        chart = [r["mint"] for r in rows[:100]]
        caps = [int(r["market_cap_lamports"]) / 1e9 for r in rows[:5]]
        out.append({"chart": chart, "caps_sol": caps, "at": mark["at"]})
    return out


if __name__ == "__main__":
    # Validate against the worked example in RULES.txt.
    fc = {
        "probabilities": [
            {"mint": "A", "place": 1, "p": 0.5},
            {"mint": "B", "place": 1, "p": 0.2},
            {"mint": "B", "place": 2, "p": 0.4},
        ],
        "top5": ["A", "B", "C", "D", "E"],
        "sizes": [
            {"place": 1, "bin": 26, "p": 0.3},
            {"place": 1, "bin": 27, "p": 0.3},
        ],
    }
    others = ["X%02d" % i for i in range(95)]
    reads = [
        {"chart": ["A", "C", "B", "F", "G"] + others, "caps_sol": [1800, 900, 800, 700, 600]},
        {"chart": ["A", "B", "C", "F", "G"] + others, "caps_sol": [2100, 1000, 900, 800, 700]},
    ]
    hm = set(["A", "B", "C", "D", "E", "F", "G"] + others)
    res = score_forecast(fc, reads, hm)
    print(res)
    # RULES expects: read1 -38.445453 (order -19.614603, size -18.830850),
    # read2 -34.255798 (order -15.424948, size -18.830850),
    # mean -36.350626 (order -17.519776, size -18.830850), agreement 28.
    assert res["per_read"][0] == (-19.614603, -18.83085, -38.445453, 13), res["per_read"][0]
    assert res["per_read"][1] == (-15.424948, -18.83085, -34.255798, 15), res["per_read"][1]
    assert res["log_score"] == -36.350626, res["log_score"]
    assert res["agreement"] == 28
    print("WORKED EXAMPLE REPRODUCED EXACTLY")
