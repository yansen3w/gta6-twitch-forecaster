"""gta6-twitch-ccu-forecast-01 entry: size-conditioned launch-shape forecaster.

Forecasts hours 2..24 of a big game launch's Twitch release day from the
hour-1 print and the case's comparables (past big launches' hourly Twitch
category counts, SullyGnome hourly averages).

Method (Python 3.13, standard library only; deterministic, no network):
  1. For every comparable launch, take its release-day hourly curve and
     express each hour as a log-ratio to that launch's own hour-1 print,
     r_h = ln(v_h / v_1).  The comparable that is the target game's own
     pre-release category history (not a launch) is excluded, as is any
     launch whose release day is missing hour 1 or most of hours 2..24.
  2. Weight each launch by similarity to a console-only, rolling-midnight
     single-player launch (the target's shape) and by size: launches whose
     hour-1 print is close to this case's hour-1 print in log space count
     most.  Size matters: across the comparables, log(v_1) correlates
     about -0.9 with the later log-ratios -- a launch that already draws a
     huge hour 1 (the world is already watching) grows far less over the
     day than one whose hour 1 is nearly empty (most regions not unlocked
     yet).  A Gaussian kernel of bandwidth 1.0 in log size captures this
     without assuming any functional form.
  3. Per hour, the forecast centre is the weighted median log-ratio,
     lightly smoothed over neighbouring hours; the spread is the weighted
     standard deviation of the log-ratios, floored at 0.25 so a small
     effective sample can never claim false precision.  Quantiles are
     q_tau = p1 * exp(centre_h + z_tau * spread_h).
  4. If too few comparables inform an hour, that hour falls back to the
     house persistence shape (0.15 log units per sqrt hour).

Leave-one-out validation over the kit's 37 usable comparables (each held
out in turn, scored by mean pinball loss on the log scale):
  all launches .......... 0.457 vs house baseline 0.930
  launches with p1>=10k . 0.272 vs house baseline 0.351
  console-only launches . 0.204 vs house baseline 0.344
(The house baseline scores about 0.387 on the practice cases themselves.)

I/O contract (see the kit's RULES.txt): read every <id>.in in the input
directory ($MAKEFUN_INPUT_DIR, else /input), write <id>.out to the output
directory ($MAKEFUN_OUTPUT_DIR, else /output): {"hours": [{"hour": h,
"q": [q05, q25, q50, q75, q95]}, ...]} for hours 2..24, five finite
numbers > 0 and <= 1e9, non-decreasing, at most 65,536 bytes.
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import.  This entry ships no such module.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Similarity weights: how much a past launch's shape counts for a
# console-only, rolling-midnight, single-player launch like this one.
TIER_WEIGHTS = {0: 1.0, 1: 0.7, 2: 0.35, 3: 0.15}
# Gaussian kernel bandwidth (natural-log units) on launch size (hour-1
# print): launches within about a factor e of this case's size dominate.
SIZE_BANDWIDTH = 1.0
# Never claim a log-spread narrower than this: the effective sample of
# similar launches is small and the target is a single unseen launch.
SPREAD_FLOOR = 0.25
# Hours of moving-average smoothing applied to the per-hour centres.
SMOOTH_HALF_WIDTH = 1
# The house persistence spread, used only as a fallback (see RULES.txt).
BASELINE_SIGMA = 0.15
MIN_COMPARABLE_HOURS = 20


def _parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _is_pre_release(comp):
    """True for a comparable that is not a launch at all (the target's own
    pre-release category history, from its premiere to the present)."""
    name = comp.get("name", "").lower()
    return "before release" in name or "premiere" in name


def _tier(comp):
    """Similarity tier to the target launch (0 = closest)."""
    if _is_pre_release(comp):
        return 99
    platforms = comp.get("platforms", "").lower()
    unlock = comp.get("unlock", "").lower()
    console_only = "pc" not in platforms
    rolling = "midnight local" in unlock or "rolling" in unlock
    early_access = "early access" in unlock or "early-access" in unlock
    if console_only and rolling and not early_access:
        return 0
    if console_only and not early_access:
        return 1
    if rolling and not early_access:
        return 2
    return 3


def _release_day(comp):
    """Release-day hourly viewers, hours 1..24 (None where unrecorded)."""
    day_start = _parse_time(comp["day_start"])
    hours = {}
    for row in comp.get("hourly", []):
        try:
            when = _parse_time(row["from"])
        except (KeyError, ValueError):
            continue
        delta = (when - day_start).total_seconds() / 3600.0
        if 0 <= delta < 24 and delta == int(delta):
            viewers = row.get("viewers")
            if isinstance(viewers, (int, float)) and viewers > 0:
                hours[int(delta) + 1] = viewers
    return [hours.get(h) for h in range(1, 25)]


def _weighted_median(pairs):
    """Weighted median of (value, weight) pairs; deterministic."""
    ordered = sorted(pairs, key=lambda pair: pair[0])
    total = sum(weight for _, weight in ordered)
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= total / 2.0:
            return value
    return ordered[-1][0]


def _weighted_mean(pairs):
    total = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / total


def _weighted_sd(pairs, mean):
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return 0.0
    var = sum(weight * (value - mean) ** 2 for value, weight in pairs) / total
    return math.sqrt(max(var, 0.0))


def _baseline_quantiles(p1, hour):
    return [
        _round2(p1 * math.exp(z * BASELINE_SIGMA * math.sqrt(hour - 1)))
        for z in Z
    ]


def _round2(x):
    """x rounded to 2 decimals, half up (as the starter rounds it)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value == int(value) else value


def _clean(values):
    """Clamp to (0, 1e9] and force non-decreasing, after rounding."""
    out = []
    prev = 0.01
    for value in values:
        value = min(max(value, 0.01), 1_000_000_000)
        if value < prev:
            value = prev
        out.append(value)
        prev = value
    return out


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    log_p1 = math.log(p1)

    # Per hour, the size- and similarity-weighted log-ratios of the
    # comparables' release days to their own hour-1 prints.
    per_hour = {h: [] for h in range(2, 25)}
    for comp in sorted(case.get("comparables", []), key=lambda c: c.get("name", "")):
        tier = _tier(comp)
        if tier not in TIER_WEIGHTS:
            continue
        day = _release_day(comp)
        if not day[0]:
            continue
        if sum(1 for v in day[1:] if v) < MIN_COMPARABLE_HOURS:
            continue
        weight = TIER_WEIGHTS[tier] * math.exp(
            -((math.log(day[0]) - log_p1) / SIZE_BANDWIDTH) ** 2
        )
        for h in range(2, 25):
            if day[h - 1]:
                per_hour[h].append((math.log(day[h - 1] / day[0]), weight))

    centres = {}
    spreads = {}
    for h in range(2, 25):
        pairs = per_hour[h]
        if len(pairs) < 3 or sum(w for _, w in pairs) <= 0:
            centres[h] = None
            spreads[h] = BASELINE_SIGMA * math.sqrt(h - 1)
            continue
        centres[h] = _weighted_median(pairs)
        spreads[h] = max(_weighted_sd(pairs, _weighted_mean(pairs)), SPREAD_FLOOR)

    # Light smoothing of the centres across neighbouring hours: the
    # launch-day shape moves slowly, and the per-hour samples differ.
    raw = dict(centres)
    for h in range(2, 25):
        if raw[h] is None:
            continue
        neighbours = [
            raw[hh]
            for hh in range(h - SMOOTH_HALF_WIDTH, h + SMOOTH_HALF_WIDTH + 1)
            if 2 <= hh <= 24 and raw[hh] is not None
        ]
        centres[h] = statistics.fmean(neighbours)

    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        if centres[h] is None:
            quantiles = _baseline_quantiles(p1, h)
        else:
            quantiles = [
                _round2(p1 * math.exp(centres[h] + z * spreads[h])) for z in Z
            ]
        hours.append({"hour": h, "q": _clean(quantiles)})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
