# pumpfun-top5-forecast-01

Forecast which five new pump.fun coins will be the largest by market cap
24 hours after the opening, with honest probabilities, for
[make.fun](https://make.fun) competition `pumpfun-top5-forecast-01`.

## Method

`main.py` (Python 3.13 standard library only, no network, no model calls)
runs a Monte Carlo diffusion of log market caps (fixed seed, 6,000
simulations x 7 answer reads) plus "phantom" newcomers, because in the
rehearsal data the top 5 is dominated by coins born minutes before the
read:

- Per-coin drift = last observed log growth, shrunk 50% toward the pool
  median (+0.068 per 10 minutes), applied only for the first 12 steps;
  volatility 0.15 (graduated/pool coins) / 0.30 (bonding-curve coins),
  diffusion saturating after 18 steps so coins do not random-walk for
  13 hours.
- Bonding-curve coins mean-revert to the ~28 SOL floor.
- Phantoms: ~2 newcomers per minute-step (max 40 per read), initial cap
  drawn from the distribution of first-appearance caps of top-5
  newcomers in the second half of history, born uniformly over the
  horizon.
- Size: Monte Carlo distribution per place, with 5% of mass left
  unnamed (anti-floor).

The horizon is read from `task.json`, not hardcoded: 1–7 steps in
practice, 43–79 steps in the final.

## Measured results (local replica scorer, rolling-cut backtest)

| cut | v1 log score | persistence baseline | delta |
|---|---|---|---|
| ≤20:20 (3 reads) | -43.2783 | -49.9581 | +6.68 |
| ≤20:30 (2 reads) | -25.9211 | -33.4776 | +7.56 |
| ≤20:40 (1 read) | -22.6324 | -29.8669 | +7.23 |
| **average** | **-34.0516** | **-41.1161** | **+7.06** |

Practice run: 24 s, 12,099-byte output, byte-identical across two runs
(deterministic). Practice baseline published in RULES: -40.408345.

## Usage

```sh
python3 main.py   # reads history.ndjson + task.json, writes forecast.json
```

## License

MIT — see `LICENSE`.
