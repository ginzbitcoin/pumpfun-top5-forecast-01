// pumpfun-top5-forecast-01's house baseline (Node 22, standard library only): persistence, the forecast that the chart
// at every answer read is the chart of the last mark (the one forecast is scored on each read, and the score is the
// mean). It reads /input/task.json (the places scored, the size bins' edges and the output file) and the last mark of
// /input/history.ndjson (its rows, the eligible coins ranked by market cap at the cut), and writes
// /output/forecast.json:
//   - place 1: 0.30 on the coin at #1 then, 0.10 on the coin at #2;
//   - place k, from 2 to 5: 0.30 on the coin at #k then, 0.10 on each of the coins at #k-1 and #k+1;
//   - the rest of each place (0.60 at place 1, 0.50 at the others) is left unnamed: the scorer shares it among the
//     answer charts' coins the forecast does not name there, the movers and the coins born after the cut alike;
//   - sizes: place k's cap a normal in log10(cap in SOL) around the log10 of the cap of the coin at #k then, sd 0.35,
//     its probability in each of the 82 bins (0.05 wide, the tails below 2.0 and from 6.0 up), each p rounded down to
//     6 decimals, a bin whose p rounds to 0 left unnamed (the rest of the place's 1 is shared by them);
//   - top5: the last mark's top 5, in its order.
// Its numbers are fixed in advance, never tuned on the practice. A prize needs a score strictly above the best house
// entry's: this one's, or the house model forecast's.
//
// Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand in for /input and /output:
//   mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out node main.ts

import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const INPUT_DIR = process.env.MAKEFUN_INPUT_DIR ?? '/input';
const OUTPUT_DIR = process.env.MAKEFUN_OUTPUT_DIR ?? '/output';
/** On the coin at #k for place k. */
const P_STAY = 0.3;
/** On each of the coins at #k-1 and #k+1 for place k. */
const P_NEIGHBOUR = 0.1;
/** The sd of a place's log10(cap in SOL) around the cap at #k then. */
const SIZE_SD = 0.35;
const MICRO = 1_000_000;

interface Row {
  rank: number;
  mint: string;
  market_cap_lamports: string | number;
}

const task = JSON.parse(readFileSync(join(INPUT_DIR, 'task.json'), 'utf8')) as { places: number; output: string; size: { edges: number[] } };
const lines = readFileSync(join(INPUT_DIR, 'history.ndjson'), 'utf8').split('\n').filter((l) => l !== '');
const marks = lines.map((l) => JSON.parse(l) as { ok: boolean; rows: Row[] | null }).filter((m) => m.ok === true && Array.isArray(m.rows));
if (marks.length === 0) throw new Error('the history holds no ok mark');
const chart = [...marks[marks.length - 1]!.rows!].sort((a, b) => a.rank - b.rank);
if (chart.length < task.places) throw new Error(`the last mark ranks ${chart.length} coins, fewer than the ${task.places} places`);

/** log10 of a cap in SOL, as the scorer takes it: log10(lamports) - 9. */
const sizeOf = (lamports: string | number): number => Math.log10(Number(BigInt(lamports))) - 9;

/** erfc(x), Numerical Recipes' erfcc (fractional error under 1.2e-7 everywhere). */
function erfc(x: number): number {
  const z = Math.abs(x);
  const t = 1 / (1 + 0.5 * z);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? r : 2 - r;
}
/** P(X >= x) for X normal with mean `mean` and sd `sd`. */
const above = (x: number, mean: number, sd: number): number => (x === -Infinity ? 1 : x === Infinity ? 0 : 0.5 * erfc((x - mean) / (sd * Math.SQRT2)));

const probabilities: Array<{ mint: string; place: number; p: number }> = [];
const sizes: Array<{ place: number; bin: number; p: number }> = [];
const edges = task.size.edges;
for (let place = 1; place <= task.places; place++) {
  probabilities.push({ mint: chart[place - 1]!.mint, place, p: P_STAY });
  if (place > 1) probabilities.push({ mint: chart[place - 2]!.mint, place, p: P_NEIGHBOUR });
  if (chart[place] !== undefined) probabilities.push({ mint: chart[place]!.mint, place, p: P_NEIGHBOUR });
  const mean = sizeOf(chart[place - 1]!.market_cap_lamports);
  for (let bin = 0; bin <= edges.length; bin++) {
    const lo = bin === 0 ? -Infinity : edges[bin - 1]!;
    const hi = bin === edges.length ? Infinity : edges[bin]!;
    const u = Math.floor((above(lo, mean, SIZE_SD) - above(hi, mean, SIZE_SD)) * MICRO);
    if (u > 0) sizes.push({ place, bin, p: u / MICRO });
  }
}
const top5 = chart.slice(0, task.places).map((r) => r.mint);
writeFileSync(join(OUTPUT_DIR, task.output), `${JSON.stringify({ probabilities, top5, sizes })}\n`);
