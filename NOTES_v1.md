# pumpfun-top5-forecast-01 — Catatan Phase 1 (v1)

Dibangun 12 Nov 2026, ~08:40–09:00 WIB. JANGAN submit dari fase ini (repo GitHub
+ submit adalah fase berikut, sesudah 09:00 WIB).

## File
- `main.py` — entry v1 (Python stdlib saja, deterministik, tanpa network/model)
- `LICENSE` — MIT (dari starter kit)
- `score.py` — replika lokal scorer (tervalidasi: contoh kerja RULES direproduksi persis)
- `backtest.py` — backtest rolling-cut v1 vs baseline starter
- `kit/` — kit yang diunduh (kit.tar.gz + unpack)
- `pf.json`, `pfr.json` — salinan referensi kompetisi/requirements
- `out_v1/forecast.json` — output v1 pada input practice (12.099 byte)

## Ringkasan RULES
- Skor = log score, rata-rata 7 answer read: order (ln p koin di tiap tempat
  top 5, floor 1e-4) + size (ln p bin market cap tiap tempat, 82 bin @ 0,05 dekade).
  Even spread = -45,059447. Tie-break: top-5 agreement (maks 175).
- Final: history s.d. 13:00 UTC 12 Nov, answer 20:00 UTC 12 Nov – 02:00 UTC 13 Nov
  (7 read/jam). Practice: rehearsal 2 jam (t0 11 Nov 20:00 UTC, 6 mark),
  answer 21:00–22:00 UTC tiap 10 menit.
- Baseline persistence (starter): skor practice -40,408345 (order -21,380389,
  size -19,027956), agreement 56. Bar hadiah = max(baseline, house model
  superbot) — skor house model TIDAK dipublikasi di RULES.
- Hadiah $200 (1st $50, 2nd $30, 3rd $24, 4th $20, 5th $16, 6th–10th $12),
  escrow Solana, klaim USDC. Kuota 10/hari + 10 total.
- Checks: repo publik + dibuat sesudah 02:00 UTC 12 Nov, LICENSE OSI,
  commit_sha, transcript bundle (thinking gate: >=30% reproduced, >=5 turn,
  usage 100% priced, >=2 file writes, semua sesi di dalam window),
  run <=300 dtk / 1 CPU / 1024 MB / deterministik 2x, tanpa model call.
- Koin lahir sesudah cut ikut dinilai tapi TIDAK bisa dinamai (baris yang
  menamai mint di luar history di-drop). Di practice: 2 dari top 5 di read
  terakhir lahir sesudah cut; 3 dari 9 pemegang top-5 lahir sesudah cut.

## Bentuk data (rehearsal)
- 6 mark (20:00 kosong, 20:10–20:50), tiap mark 121–200 baris (top 200),
  454 mint berbeda. Eligible tumbuh 235 → 1.434 per 10 menit.
- Top 5 didominasi koin BARU: tiap mark 1–4 pendatang baru langsung top 5,
  lahir 5–20 menit sebelumnya, langsung pool (graduated) di 800–3.000 SOL.
- Koin curve runtuh ke lantai ~28 SOL dalam 1 mark (CHAD 132→28, Squirrel
  96→28); koin pool bertahan & tumbuh ~+0,06 log10/10 menit (Claude
  1.086→1.912 SOL dalam 40 menit; AIB 2.940→3.638).
- Cap tempat 1: 1.086 → 3.638 SOL dalam 40 menit; tempat 2–5 merapat
  (~2.000 SOL di 20:50). Top 5 read terakhir practice: Max, MIHAO VI,
  Google, NIHAONOON, HAMSTER (hanya Google dari top 5 20:50).

## Model v1 (main.py)
Monte Carlo difusi log-cap (seed tetap, 6.000 sim × 7 read) + pendatang phantom:
- Drift per koin = pertumbuhan log terakhir, di-shrink 50% ke median pool
  (+0,068/10 menit), hanya 12 step pertama; vol 0,15 (pool) / 0,30 (curve),
  difusi dijenuhkan di 18 step (koin tidak random-walk 13 jam).
- Koin curve mean-revert ke lantai 28 SOL.
- Phantom: ~2 pendatang/menit-step (maks 40/read), cap awal dari distribusi
  cap kemunculan pertama pendatang top-5 paruh akhir history, lahir seragam
  sepanjang horizon. Share tempat phantom: practice 0,20–0,27, final-shape 0,47–0,56.
- Size: distribusi MC per tempat, 5% massa dibiarkan unnamed (anti-floor).
- Horizon dibaca dari task.json (bukan hardcode): practice 1–7 step,
  final 43–79 step.

## Hasil ukur (backtest rolling-cut, scorer replika, 6 read)
| cut | v1 log | baseline log | selisih |
|---|---|---|---|
| ≤20:20 (3 read) | -43,2783 | -49,9581 | +6,6799 |
| ≤20:30 (2 read) | -25,9211 | -33,4776 | +7,5565 |
| ≤20:40 (1 read) | -22,6324 | -29,8669 | +7,2345 |
| **RATA-RATA** | **-34,0516** | **-41,1161** | **+7,0645** |
(order +1,79; size +5,27 — keunggulan terbesar di size: baseline memusatkan
size di cap terakhir sd 0,35, padahal cap tumbuh cepat.)
- Practice v1: 24 detik, 51 baris probabilitas, 188 baris size, 12.099 byte.
  2 run byte-identik (deterministik). Format lolos validasi.
- Final-shape sintetis (66 mark): 28–42 detik, place-sum 0,40–0,47
  (vs 0,06–0,12 sebelum saturasi vol) — masih jauh di bawah batas 300 detik.
- top5 v1 (practice): AIB, MIHAO VI, SELONMUSK, Google, WAGMI — MIHAO VI
  (#2) dan Google (#3) memang top 5 read terakhir practice.

## Verdict
**LAYAK submit v1** — kalahkan baseline +7,06 nats di semua cut backtest,
tanpa satu pun cut kalah. Caveat: backtest horizon 10–30 menit, sedangkan
practice 60 menit dan final 7–13 jam; keunggulan size/order di horizon
panjang adalah ekstrapolasi model (difusi + pendatang), bukan pengukuran
langsung. Skor house model tidak diketahui — bar hadiah sebenarnya baru
terlihat sesudah submit pertama (skor practice tampil saat masuk).

## Langkah berikut (fase berikut, bukan fase ini)
1. Buat repo GitHub publik (SESUDAH 09:00 WIB), push main.py + LICENSE.
2. Bundle transkrip sesi ini + submit v1; catat skor practice yang tampil.
3. Bila skor practice v1 > baseline practice (-40,408345) dengan margin
   jelas → biarkan sebagai entry final sementara; bila < baseline → iterasi:
   kalibrasi ulang (arrival rate, sigma pool, P_MIN_NAME) di backtest.
4. Iterasi lanjutan yang menjanjikan: (a) bobot drift per usia koin muda;
   (b) pisah vol koin mapan vs koin muda; (c) uji P_MIN_NAME 0,002 vs 0,008.
