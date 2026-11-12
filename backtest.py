"""Rolling-cut backtest for pumpfun-top5-forecast-01.

For each cut (train on marks up to index k, score on the later marks as
pseudo-answer reads), run a forecaster and the house baseline starter on the
truncated history, and score both with the exact local scorer (score.py).

Caveat: backtest horizons are 10-30 min, the practice is 60 min and the
final 7-13 h, so this measures short-horizon skill and the machinery, not
the final number. The forecaster's horizon handling (task.json reads) is
what carries the skill to the longer horizons.
"""
import json
import os
import subprocess
import sys

WORK = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(WORK, "pumpfun-top5-forecast-01-kit")
sys.path.insert(0, WORK)
from score import history_mints_from, reads_from_marks, score_forecast  # noqa: E402


def load_marks():
    with open(os.path.join(KIT, "input", "history.ndjson")) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def write_cut_input(cut_idx, held):
    d = os.path.join(WORK, "backtest", "cut%d" % cut_idx)
    os.makedirs(os.path.join(d, "in"), exist_ok=True)
    os.makedirs(os.path.join(d, "out_v1"), exist_ok=True)
    os.makedirs(os.path.join(d, "out_base"), exist_ok=True)
    with open(os.path.join(d, "in", "history.ndjson"), "w") as fh:
        for m in MARKS[: cut_idx + 1]:
            fh.write(json.dumps(m) + "\n")
    with open(os.path.join(KIT, "input", "task.json")) as fh:
        task = json.load(fh)
    task["reads"] = [m["at"] for m in held]
    task["history_until"] = held[0]["at"]
    task["marks"] = cut_idx + 1
    with open(os.path.join(d, "in", "task.json"), "w") as fh:
        json.dump(task, fh)
    return d


def run(cmd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=WORK)
    return r


def main():
    global MARKS
    MARKS = load_marks()
    cuts = [(2, MARKS[3:]), (3, MARKS[4:]), (4, MARKS[5:])]
    tot_v1, tot_base = [], []
    for cut_idx, held in cuts:
        d = write_cut_input(cut_idx, held)
        env = {
            "MAKEFUN_INPUT_DIR": os.path.join(d, "in"),
        }
        r1 = run(
            [sys.executable, os.path.join(WORK, "main.py")],
            {**env, "MAKEFUN_OUTPUT_DIR": os.path.join(d, "out_v1")},
        )
        r2 = run(
            ["node", os.path.join(KIT, "starter", "main.ts")],
            {**env, "MAKEFUN_OUTPUT_DIR": os.path.join(d, "out_base")},
        )
        for name, r in (("v1", r1), ("base", r2)):
            if r.returncode != 0:
                print("cut %d %s FAILED rc=%d" % (cut_idx, name, r.returncode))
                print(r.stdout[-2000:])
                print(r.stderr[-2000:])
                return 1
        hm = history_mints_from(os.path.join(d, "in", "history.ndjson"))
        reads = reads_from_marks(held)
        with open(os.path.join(d, "out_v1", "forecast.json")) as fh:
            f_v1 = json.load(fh)
        with open(os.path.join(d, "out_base", "forecast.json")) as fh:
            f_base = json.load(fh)
        s_v1 = score_forecast(f_v1, reads, hm)
        s_base = score_forecast(f_base, reads, hm)
        tot_v1.append(s_v1)
        tot_base.append(s_base)
        print(
            "cut<=%s (%d reads %s): v1 log=%.4f (ord %.4f, size %.4f, agr %d) | "
            "base log=%.4f (ord %.4f, size %.4f, agr %d) | diff %+.4f"
            % (
                MARKS[cut_idx]["at"][11:16],
                len(reads),
                ",".join(r["at"][11:16] for r in reads),
                s_v1["log_score"], s_v1["order_score"], s_v1["size_score"],
                s_v1["agreement"],
                s_base["log_score"], s_base["order_score"], s_base["size_score"],
                s_base["agreement"],
                s_v1["log_score"] - s_base["log_score"],
            )
        )
    n = sum(len(c[1]) for c in cuts)
    mean_v1 = sum(s["log_score"] * len(c[1]) for s, c in zip(tot_v1, cuts)) / n
    mean_base = sum(s["log_score"] * len(c[1]) for s, c in zip(tot_base, cuts)) / n
    o_v1 = sum(s["order_score"] * len(c[1]) for s, c in zip(tot_v1, cuts)) / n
    o_base = sum(s["order_score"] * len(c[1]) for s, c in zip(tot_base, cuts)) / n
    z_v1 = sum(s["size_score"] * len(c[1]) for s, c in zip(tot_v1, cuts)) / n
    z_base = sum(s["size_score"] * len(c[1]) for s, c in zip(tot_base, cuts)) / n
    print(
        "MEAN over %d reads: v1 log=%.4f (ord %.4f, size %.4f) | "
        "base log=%.4f (ord %.4f, size %.4f) | diff %+.4f"
        % (n, mean_v1, o_v1, z_v1, mean_base, o_base, z_base, mean_v1 - mean_base)
    )


if __name__ == "__main__":
    main()
