#!/usr/bin/env python3
"""Forecast GTA VI launch-day Twitch viewers, hour by hour.

Entry for make.fun competition gta6-twitch-ccu-forecast-01.

Method (from the kit data alone, no network, no model calls):
  * The case gives hour 1's print (viewers in 00:00-01:00 UTC of release
    day) plus the hourly curves of ~38 past big game launches
    ("comparables"), each from 14 days before to 3 days after its own
    release day.
  * Past launches split into two regimes. Launches whose hour-1 print
    is large (already live at midnight UTC: New Zealand / Australia /
    Europe already unlocked) keep a tame intraday shape: they dip a
    little overnight, then rise into the evening peak, staying within
    roughly 0.3x-2.6x of hour 1. Launches whose hour-1 print is tiny
    (still locked at midnight UTC, unlocking later in the day) explode
    10x-2000x later, on a schedule nothing in hour 1 can predict.
  * So the forecast anchors on hour 1 and borrows the shape from the
    launches that look like this one: comparables with a complete
    release-day curve and an hour-1 print of at least 20,000 viewers.
    For each forecast hour h, the median is hour1 * exp(weighted median
    of log(viewers_h / viewers_1)), weighted by a Gaussian kernel on
    log(hour-1 print) with bandwidth 1.2 -- mega-launches borrow their
    shape from other mega-launches. The spread is the interquartile
    range of those log-ratios (sd = IQR / 1.349, floored at 0.15 and
    capped at 0.9), mapped through the standard normal quantiles.
  * If hour 1 is small (< 20,000: the launch was still locked at
    midnight UTC), the same machinery runs on every complete curve
    with a much wider spread (sd floored at 0.6, capped at 2.0),
    because the unlock hour is unknown and the shape is far less
    predictable.

Validation (leave-one-out backtest on the kit's own comparables,
37 complete release-day curves; pinball loss on the log scale):
  * this model on big hour-1 launches: mean loss 0.258
  * house baseline (flat at hour 1, 0.15*sqrt(h-1) spread): 0.321
  * the house baseline scores about 0.387 on the real practice cases.

Deterministic: pure functions of the input file, no randomness, no
clock, no network. Standard library only. Runs in well under a second.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = (-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722)
HOURS = tuple(range(2, 25))

BANDWIDTH = 1.2          # Gaussian kernel bandwidth on log(hour-1 print)
BIG_V1 = 20000.0         # hour-1 print that marks "already live" launches
MIN_BIG_POOL = 8         # need at least this many big launches, else fall back
SD_FLOOR = 0.15
SD_CAP = 0.9
SD_FLOOR_SMALL = 0.6     # wider spread when hour 1 was still locked
SD_CAP_SMALL = 2.0
BASELINE_SPREAD = 0.15   # house baseline spread factor, fallback only


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_points(comp):
    """Return {hour: viewers} for a comparable's release day, or None.

    Hour 1 is the point at day_start; hours 2-24 the points that
    follow. A point counts as present only when its viewers value is
    a number. The comparable is unusable when hour 1 is missing.
    """
    try:
        day_start = parse_ts(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return None
    points = {}
    for row in comp.get("hourly") or []:
        try:
            at = parse_ts(row["from"])
            viewers = row["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(viewers, (int, float)) or isinstance(viewers, bool):
            continue
        hour = int((at - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            points[hour] = max(float(viewers), 1.0)
    if 1 not in points:
        return None
    return points


def weighted_median(pairs):
    """Median of values with weights: first value whose cumulative
    weight reaches half the total. `pairs` is a list of (value, weight)
    with non-negative weights. When every weight underflows to zero
    (a target hour-1 print orders of magnitude from every past
    launch), fall back to the plain median instead of dividing by
    zero."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0.0:
        values = [value for value, _ in ordered]
        return values[len(values) // 2] if values else 0.0
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= total / 2.0:
            return value
    return ordered[-1][0]


def quantile(sorted_values, q):
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def forecast_case(case):
    known = case.get("known") or []
    hour1 = 1.0
    for row in known:
        if row.get("hour") == 1:
            hour1 = max(float(row.get("viewers") or 1), 1.0)
            break
    else:
        if known:
            hour1 = max(float(known[0].get("viewers") or 1), 1.0)

    # Build the pool of past launches with a usable release-day curve.
    pool = []  # (hour-1 viewers, {hour: viewers})
    for comp in case.get("comparables") or []:
        points = release_day_points(comp)
        if points is None:
            continue
        have = sum(1 for h in HOURS if h in points)
        if have < 20:
            continue
        pool.append((points[1], points))

    big = [(v1, pts) for v1, pts in pool if v1 >= BIG_V1]
    if hour1 >= BIG_V1 and len(big) >= MIN_BIG_POOL:
        use, sd_floor, sd_cap = big, SD_FLOOR, SD_CAP
    else:
        use, sd_floor, sd_cap = pool, SD_FLOOR_SMALL, SD_CAP_SMALL

    log_v1 = math.log(hour1)
    rows = []
    for hour in HOURS:
        pairs = []
        for comp_v1, points in use:
            if hour in points:
                log_ratio = math.log(points[hour] / comp_v1)
                weight = math.exp(-((math.log(comp_v1) - log_v1) / BANDWIDTH) ** 2)
                pairs.append((log_ratio, weight))
        if not pairs:
            # No past launch covers this hour: fall back to the house
            # baseline's flat median with its widening spread.
            spread = BASELINE_SPREAD * math.sqrt(hour - 1)
            quantiles = [hour1 * math.exp(z * spread) for z in Z]
        else:
            median = weighted_median(pairs)
            logs = sorted(value for value, _ in pairs)
            sd = (quantile(logs, 0.75) - quantile(logs, 0.25)) / 1.349
            sd = min(max(sd, sd_floor), sd_cap)
            quantiles = [hour1 * math.exp(median + z * sd) for z in Z]
        # Output contract: finite, > 0, <= 1e9, non-decreasing.
        fixed = []
        prev = 0.0
        for q in quantiles:
            q = max(q, 1.0)
            q = max(q, prev)
            q = min(q, 1_000_000_000.0)
            fixed.append(round(q, 2))
            prev = fixed[-1]
        rows.append({"hour": hour, "q": fixed})
    return {"hours": rows}


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(os.listdir(in_dir)):
        if not name.endswith(".in"):
            continue
        with open(os.path.join(in_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        result = forecast_case(case)
        out_path = os.path.join(out_dir, case["id"] + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
