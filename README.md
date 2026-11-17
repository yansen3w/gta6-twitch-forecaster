# gta6-twitch-forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/yansen3w/gta6-twitch-forecaster/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/yansen3w/gta6-twitch-forecaster/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts Grand Theft Auto VI's launch-day Twitch viewers hour by hour. Given the first hour's viewer count, it predicts hours 2–24 as five quantiles each (0.05, 0.25, 0.5, 0.75, 0.95), learned from 38 past big game launches: each launch's release-day shape is expressed as log-ratios to its own hour-1 count, weighted by how similar the launch is to a console-only rolling-midnight release and by how close its hour-1 size is to this launch's. Leave-one-out validation over the comparables: mean pinball loss 0.457 overall and 0.204 on console-only launches, vs 0.930 / 0.344 for the house persistence baseline.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only. Reads every `<id>.in` in the input directory and writes `<id>.out` (23 rows, hours 2–24) to the output directory.

---

<sub>Entered on [make.fun](https://make.fun/?ref=30afxf5j&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
