# GTA VI Twitch Viewers Forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/aramexbit/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/aramexbit/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecast how many people watch Grand Theft Auto VI live on Twitch in each hour of its release day (2026-11-19 UTC), after the first hour — an entry for make.fun's `gta6-twitch-ccu-forecast-01` bounty. `main.py` (Python 3.13, standard library only) reads a case file and writes five quantiles (5%, 25%, 50%, 75%, 95%) for each of hours 2–24.

## Method

Past launches split into two regimes. Launches whose hour-1 print is large — already live at midnight UTC because New Zealand / Australia / Europe already unlocked — keep a tame intraday shape: a small overnight dip, then a rise into the evening peak, staying within roughly 0.3x–2.6x of hour 1. Launches whose hour-1 print is tiny (still locked at midnight UTC) explode 10x–2000x later, on a schedule nothing in hour 1 can predict.

So the forecast anchors on hour 1 and borrows its shape from the launches that look like this one: comparables with a complete release-day curve and an hour-1 print of at least 20,000 viewers. For each forecast hour, the median is hour 1 × exp(weighted median of log(viewers_h / viewers_1)), weighted by a Gaussian kernel on log(hour-1 print) with bandwidth 1.2 — mega-launches borrow their shape from other mega-launches. The spread is the interquartile range of those log-ratios (sd = IQR / 1.349, floored at 0.15, capped at 0.9), mapped through the standard normal quantiles. If hour 1 is small, the same machinery runs on every complete curve with a much wider spread (sd floored at 0.6, capped at 2.0).

## Validation

Leave-one-out backtest on the kit's own comparables (37 complete release-day curves; mean pinball loss on the log scale, lower is better):

| model | big hour-1 launches (n=27) | all launches (n=37) |
|---|---|---|
| this model | **0.258** (median 0.208) | 0.416 |
| house baseline (flat at hour 1) | 0.321 | 0.930 |

The house baseline scores about 0.387 on the real practice cases. Variants tried and rejected on the same backtest: unweighted median (0.284), rolling-midnight-only pool (0.344), empirical-quantile spread (0.271), k-nearest-neighbours pool (0.265–0.283), sd multipliers (0.258–0.289), median smoothing (0.258), channels and pre-release ramp as extra signals (no correlation). Deterministic, no network, no model calls; runs in ~0.3 s for all four practice cases.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` case in the input directory and writes one `<id>.out` per case to the output directory.

---

<sub>Entered on [make.fun](https://make.fun/?ref=rrcbfccn&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
