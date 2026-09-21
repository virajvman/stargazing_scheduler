# Stargazing Scheduler

Observing schedules for the Stanford student observatory. Pick a night and a set
of telescopes, get one spreadsheet per telescope.

**Web app:** https://virajvman.github.io/stargazing_scheduler/

There is nothing to install to use it — the page runs the same `code.py` the
notebook uses, in your browser, via [Pyodide](https://pyodide.org/).

## How targets are chosen

The window is split into equal intervals. In each interval every telescope is
scored on what it can currently reach: higher in the sky is better, and a target
about to sink below the altitude floor counts as more urgent, so it gets used
before it is lost. Three rules then shape which object each telescope gets.

### 1. The eVscopes stay away from the zenith

Their mounts track poorly overhead, so they are capped at 80°
(`ZENITH_LIMIT_EVSCOPE`). This is a *band*, not a ban — a target that culminates
overhead is still scheduled earlier or later in the night, on its way up or down.
Other telescopes are uncapped and will happily take a target at 84°.

### 2. The domes show the same category at the same time

Nobody realistically gets to both domes in one visit, so both are pushed onto the
same category in each interval. Whichever dome you walk into, you work through a
cluster, then a nebula, then a galaxy — instead of seeing a cluster in one dome
and, an hour later, another cluster in the other.

### 3. The portables show different categories at the same time

Visitors walk the whole portable line in one go, so the portables are pushed onto
*different* categories at any given moment. Five telescopes, five kinds of
object, a few minutes.

### These are preferences, not constraints

Rules 2 and 3 are score terms (`COUPLING_WEIGHT`, worth 150 against object scores
that run 30–190), so when the lists or the sky will not cooperate they lose and
you still get a schedule. The page reports how many intervals each rule actually
held, and why it fell short when it did.

Only these are hard: the altitude band, one object per telescope per night, and
no two telescopes in a group on the same object simultaneously. Even the first
relaxes as a last resort — if a telescope has nothing new in reach it will repeat
an earlier target rather than fail, and says so.

A fourth, milder term (`SEQUENCE_VARIETY_PENALTY`) nudges each individual
telescope to rotate categories over the night rather than sitting on one kind.

### How many targets per telescope

Left on `auto`, the count comes from `recommend_slots()`, bounded by whichever
binds first:

| bound | meaning |
| --- | --- |
| time | window length ÷ the slowest telescope's `minutes_per_target` |
| targets | a telescope can only reach so many objects tonight |
| matching | for a matched group, more targets than the lists can agree on would only repeat categories |

Override it per group under **Options** if a night feels rushed or draggy, and
adjust `minutes_per_target` in `target_lists.py` if the default pacing is wrong.

## Adding or changing targets

1. Edit the lists in [`target_lists.py`](target_lists.py).
2. Regenerate the coordinate cache the web app reads:

```bash
python scripts/build_catalog.py
```

3. Commit both files. The web app picks them up on the next page load — it fetches
   `code.py` and `target_lists.py` directly, so there is no build step and no
   second copy to keep in step.

Coordinates are cached because the browser cannot query SIMBAD (`astroquery` is
not available under Pyodide, and SIMBAD does not serve cross-origin requests).
Deep-sky coordinates never change, so this costs nothing. Planets and the Moon
are computed live from astropy's built-in ephemeris.

### Dome matching is limited by the 24-inch's list

Worth knowing if the domes often fail to match: the 24-inch list is 8 clusters, 2
nebulae, 2 planets and **no galaxies**, so galaxies can never be matched however
many the 0.7 m has. Measured over a year of test nights, adding 3 galaxies and 2
nebulae to the 24-inch list moved dome matching from 64% to 88% — far more than
any weight tuning does.

## Using it from Python

```python
import json
from code import schedule_night, register_coordinates
from target_lists import build_roster

#skip SIMBAD by loading the cached coordinates
register_coordinates(json.load(open("web/catalog.json"))["objects"])

out = schedule_night(
    "2026-08-11", "21:00", "22:30",
    roster=build_roster({"24inch": 1, "07m": 1, "evscope": 2, "5SE": 1, "10Dob": 2}),
    write_csv=True,          # -> output/catalog_<label>.csv
)

for group in out["groups"]:
    print(group["name"], group["num_slots"], group["recommendation"]["reason"])
```

`main_scheduler()` still schedules one telescope at a time with explicit
per-category counts, as [`make_schedule.ipynb`](make_schedule.ipynb) uses it. It
now takes a `max_altitude` argument and runs on the same core, so single-telescope
output is unchanged.

## Tests

```bash
python tests/test_scheduling.py
```

Runs offline against the cached catalog and checks each rule over a year of
dates, including that the zenith cap and the category coupling each *change the
answer* — a rule that quietly stopped applying would otherwise still pass.

## Hosting

GitHub Pages, served from the repository root on `main`
(Settings → Pages → Source: `main` / `/root`). `.nojekyll` keeps Jekyll from
touching the files. Serving from the root is deliberate: it lets the page fetch
`code.py` and `target_lists.py` in place, so the notebook and the website cannot
drift apart.

To run it locally:

```bash
python -m http.server 8765
```

Then open http://localhost:8765.
