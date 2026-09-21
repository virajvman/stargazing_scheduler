# Stargazing Scheduler

Builds observing schedules for the Stanford student observatory telescopes.
Pick a night, get a spreadsheet per telescope.

### → **[Open the scheduler](https://virajvman.github.io/stargazing_scheduler/)**

Nothing to install. It runs in the browser, so the first load takes ~15 seconds
while it fetches Python and astropy, then it is instant.

**Download spreadsheet** gives one `.xlsx` with every telescope on a single
sheet, ready to import into Google Sheets. **CSVs** gives one file per telescope.

## Location

All altitudes are computed for the observatory in **Palo Alto, CA**
(37.4419° N, 122.1430° W, 90 m), and all times are local Pacific.
Set in `palo_alto_location` in [`code.py`](code.py).

## Target lists

[`target_lists.py`](target_lists.py) holds everything about what we point at:

| | |
| --- | --- |
| `objects_24inch`, `objects_07m`, `objects_ev`, … | what each telescope can show, by category |
| `TELESCOPE_MODELS` | the telescopes, how many exist, and each one's zenith limit |
| `common_name` | "M57" → "Ring Nebula" |
| `cluster_types` | which clusters are open vs globular |
| `outreach_link`, `outreach_link_by_object` | the links that go in the sheet |

After editing a target list, regenerate the coordinates the website reads:

```bash
python scripts/build_catalog.py
```

Then commit both files. Deep-sky coordinates are cached because the browser
cannot query SIMBAD; planets and the Moon are computed live.

## The scripts

| | |
| --- | --- |
| [`code.py`](code.py) | the scheduler — observability, altitudes, and target choice |
| [`target_lists.py`](target_lists.py) | the telescopes and their targets |
| [`spreadsheet.py`](spreadsheet.py) | writes the combined `.xlsx` |
| [`scripts/build_catalog.py`](scripts/build_catalog.py) | resolves targets via SIMBAD into `web/catalog.json` |
| [`tests/test_scheduling.py`](tests/test_scheduling.py) | `python tests/test_scheduling.py` |
| [`make_schedule.ipynb`](make_schedule.ipynb) | the notebook, for plots and poking at internals |
| `index.html`, `web/` | the website, which runs `code.py` in the browser |

## How targets get chosen

The night is split into equal slots. In each slot every telescope is scored on
what it can reach — higher is better, and a target about to set counts as more
urgent so it gets used before it is lost. On top of that:

- **The eVscopes stop at 80°**, since they track poorly near the zenith. A target
  passing overhead is still used earlier or later, on its way up or down.
- **Telescopes in a group show different categories at the same time.** For the
  portable line, visitors walk all of them in one go. For the two domes, the
  24-inch is an eyepiece and the 0.7 m takes long exposures, so keeping them
  apart lets each do what only it can.
- **Each telescope rotates categories** over the night, so whoever stays at one
  sees variety.

These are preferences, not rules: when the sky or the lists will not allow it,
you still get a schedule, and the page says what it could not manage and why.

Under **Options** you can change how many targets each telescope gets, how many
of each category, and whether a group is varied or matched.

## Notes

- Target counts default to a suggestion based on the window length, how long each
  telescope needs per object (`minutes_per_target`), and what is actually up.
- Every scheduled target comes with three **alternates**, for when something goes
  wrong or you are ahead of schedule.
- Clicking the `68° rising` under an object shows its elevation across that slot.
- The site is served by GitHub Pages from `main` at `/ (root)`, which lets the
  page load `code.py` directly — the notebook and the website run the same code.
  Pages caches for 10 minutes, so a change takes that long to appear, or a hard
  refresh.
