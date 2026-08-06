---
title: Playtest Tracker
description: Track when each country was last playtested and see the results on a world map.
---

The playtest tracker records when each country was last playtested and renders the results as a world map, so the countries most in need of a fresh playtest are easy to spot at a glance.

**[Open the playtest map](https://millenniumdawn.github.io/Millennium-Dawn/playtest-map/)**

Light blue means recently playtested, dark blue means stale (capped at 365+ days), and the darkest shade also marks countries never playtested. Hover a country for its tag, last playtest date, and days since. Entities without their own world-map geometry (Kosovo, Somaliland, the Shan states, and similar) are tracked too and appear in the table below the map.

# How it works

- [`tools/playtest/last_playtested.csv`](https://github.com/MillenniumDawn/Millennium-Dawn/blob/main/tools/playtest/last_playtested.csv) holds one row per country tag with the date of its most recent playtest in `YYYY-MM-DD` format. A blank date means never playtested.
- [`tools/playtest/generate_playtest_map.py`](https://github.com/MillenniumDawn/Millennium-Dawn/blob/main/tools/playtest/generate_playtest_map.py) compiles the CSV into the interactive map (requires `pip install plotly` to run locally).
- GitHub Actions regenerates the map and republishes this site whenever the CSV changes on `main`.

# Recording a playtest

1. Edit `tools/playtest/last_playtested.csv` and set the country's `last_playtested` column to the session date.
2. Commit and push (or merge a PR). The map on this site updates automatically.
