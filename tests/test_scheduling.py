#!/usr/bin/env python3
"""Checks for the three telescopes-at-once rules.

Runs without pytest and without SIMBAD (it reads the committed coordinate
catalog), so it is safe to run anywhere:

    python tests/test_scheduling.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import code as sched
import target_lists as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#nights spread through the year, so a seasonal quirk cannot hide a regression
DATES = ["2026-01-16", "2026-02-20", "2026-03-20", "2026-04-17", "2026-05-15",
         "2026-06-19", "2026-07-17", "2026-08-11", "2026-09-21", "2026-10-16",
         "2026-11-20", "2026-12-18"]

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  pass  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  --- {detail}" if detail else ""))
        failures.append(name)


def load_catalog():
    with open(os.path.join(ROOT, "web", "catalog.json")) as f:
        catalog = json.load(f)
    sched.register_coordinates(catalog["objects"])
    return catalog


def nights(**kwargs):
    """Schedule every test date with the standard roster."""
    for date in DATES:
        yield date, sched.schedule_night(
            date, "20:00", "22:00", roster=T.build_roster(), verbose=False, **kwargs)


def rows_of(out, label):
    df = out["telescopes"][label]["schedule"]
    return [r for _, r in df.iterrows() if r["object"] is not None]


def test_catalog_covers_every_target(catalog):
    print("\ncoordinate catalog")
    missing = []
    for model, spec in T.TELESCOPE_MODELS.items():
        for cls in T.OBJECT_CLASSES:
            if cls == "planet":
                continue
            for name in spec["targets"].get(cls, []):
                if name not in catalog["objects"]:
                    missing.append(f"{name} ({model})")
    check("every deep-sky target has coordinates", not missing,
          f"missing: {', '.join(sorted(set(missing)))} --- rerun scripts/build_catalog.py")


def test_zenith_cap():
    print("\nrule 1: the eVscopes stay away from the zenith")
    cap = T.ZENITH_LIMIT_EVSCOPE
    worst = 0.0
    worst_where = ""
    for date, out in nights():
        for label, tel in out["telescopes"].items():
            if not label.startswith("evscope"):
                continue
            for r in rows_of(out, label):
                if r["elev"] > worst:
                    worst, worst_where = r["elev"], f"{label} on {date}: {r['object']}"
    check(f"no eVscope target above {cap:.0f} deg", worst <= cap,
          f"highest was {worst} deg --- {worst_where}")

    #and the cap must actually bite, or the test above proves nothing
    uncapped = T.build_roster()
    for inst in uncapped:
        if inst["model"] == "evscope":
            inst["max_altitude"] = None
    over = 0
    for date in DATES:
        out = sched.schedule_night(date, "20:00", "22:00", roster=uncapped, verbose=False)
        for label in [l for l in out["telescopes"] if l.startswith("evscope")]:
            over += sum(1 for r in rows_of(out, label) if r["elev"] > cap)
    check("without the cap, the eVscopes would go overhead", over > 0,
          "removing the cap changed nothing, so the cap is not being exercised")


def test_no_target_twice_at_once():
    print("\nno two telescopes in a group on the same object at the same time")
    clashes = []
    for date, out in nights():
        for g in out["groups"]:
            per = {l: rows_of(out, l) for l in g["telescopes"]}
            n = min((len(v) for v in per.values()), default=0)
            for k in range(n):
                names = [per[l][k]["object"] for l in g["telescopes"]]
                if len(set(names)) != len(names):
                    clashes.append(f"{date} {g['name']} slot {k}: {names}")
    check("every telescope has its own object in each slot", not clashes,
          "; ".join(clashes[:3]))


def test_dome_matching_and_portable_variety():
    print("\nrules 2 and 3: domes match, portables differ")
    stats = {"match": [0, 0], "diverse": [0, 0]}
    for date, out in nights():
        for g in out["groups"]:
            per = {l: rows_of(out, l) for l in g["telescopes"]}
            if len(per) < 2:
                continue
            n = min(len(v) for v in per.values())
            for k in range(n):
                classes = [per[l][k]["type"] for l in g["telescopes"]]
                distinct = len(set(classes))
                want = (distinct == 1) if g["coupling"] == "match" else (distinct == len(classes))
                stats[g["coupling"]][0] += want
                stats[g["coupling"]][1] += 1

    m_hit, m_tot = stats["match"]
    d_hit, d_tot = stats["diverse"]
    print(f"        domes matched {m_hit}/{m_tot}, portables varied {d_hit}/{d_tot}")

    #Thresholds are deliberately below what we measure now. Perfect compliance is
    #impossible --- a telescope with no galaxies cannot match one showing a galaxy
    #--- so these guard against a real regression, not against the sky.
    check("domes match in most slots", m_tot and m_hit / m_tot >= 0.75,
          f"{m_hit}/{m_tot}")
    check("portables differ in most slots", d_tot and d_hit / d_tot >= 0.80,
          f"{d_hit}/{d_tot}")

    #coupling must beat not coupling, otherwise it is doing nothing
    loose = [{"name": "Dome telescopes",
              "telescopes": [t["label"] for t in T.build_roster() if t["kind"] == "dome"],
              "coupling": "none"}]
    none_hit = none_tot = 0
    for date in DATES:
        out = sched.schedule_night(date, "20:00", "22:00", roster=T.build_roster(),
                                   groups=loose, verbose=False)
        g = out["groups"][0]
        per = {l: rows_of(out, l) for l in g["telescopes"]}
        n = min(len(v) for v in per.values())
        for k in range(n):
            classes = [per[l][k]["type"] for l in g["telescopes"]]
            none_hit += len(set(classes)) == 1
            none_tot += 1
    print(f"        with coupling off, domes would match {none_hit}/{none_tot}")
    check("matching beats not matching", m_hit / m_tot > none_hit / none_tot,
          f"coupled {m_hit}/{m_tot} vs uncoupled {none_hit}/{none_tot}")


def test_never_hard_fails():
    print("\na thin night degrades instead of blowing up")
    errors = []
    for date in DATES:
        for window in [("20:00", "22:00"), ("19:30", "23:30"), ("22:00", "22:40")]:
            try:
                sched.schedule_night(date, window[0], window[1],
                                     roster=T.build_roster(), verbose=False)
            except Exception as exc:
                errors.append(f"{date} {window[0]}-{window[1]}: {exc}")
    check("every date and window produces a schedule", not errors,
          "; ".join(errors[:2]))


def test_contended_object_is_not_double_booked():
    print("\ntwo telescopes wanting the one object left")
    #both lists hold a single planet, so there is nothing to share out
    thin = {"cluster": [], "nebula": [], "galaxy": [], "point": [],
            "planet": ["jupiter"], "telescope_type": "thin"}
    tels = [{"label": "a", "display": "A", "targets": thin,
             "max_altitude": None, "minutes_per_target": 20},
            {"label": "b", "display": "B", "targets": thin,
             "max_altitude": None, "minutes_per_target": 20}]

    out = sched.schedule_group("2026-04-17", "21:00", "22:00", tels, 1,
                               coupling="diverse", verbose=False)
    picked = [out[l]["schedule"]["object"].iloc[0] for l in ("a", "b")]
    real = [p for p in picked if p is not None]
    check("one telescope gets it, the other gets an open slot",
          len(real) == 1 and len(set(real)) == 1, str(picked))
    check("and the open slot is explained", any(out["a"]["group_notes"]))


def test_slot_recommendation():
    print("\nsuggested target counts")
    roster = T.build_roster()
    domes = [t for t in roster if t["kind"] == "dome"]

    short = sched.recommend_slots("2026-08-11", "21:00", "22:30", domes)
    long_ = sched.recommend_slots("2026-08-11", "20:00", "23:00", domes)
    check("a longer window suggests at least as many targets",
          long_["num_slots"] >= short["num_slots"],
          f"{short['num_slots']} for 90 min vs {long_['num_slots']} for 180 min")
    check("the suggestion respects the slowest telescope's pace",
          short["num_slots"] <= short["window_minutes"] // short["pace"] or
          short["num_slots"] == 1,
          str(short))
    check("the suggestion never exceeds what is observable",
          long_["num_slots"] <= long_["available"], str(long_))


def test_quotas_and_back_compat():
    print("\nthe old per-telescope entry point still works")
    out = sched.main_scheduler(
        "2026-08-11", "21:00", "22:30",
        num_cluster=1, num_galaxy=2,
        telescope_objs_dict=T.objects_07m, min_altitude=30, verbose=False)
    types = out["df_schedule"]["type"].tolist()
    check("per-category counts are honoured",
          types.count("cluster") == 1 and types.count("galaxy") == 2,
          str(types))
    check("it still returns what the notebook plots",
          all(k in out for k in ("time_local_datetimes", "alts_cluster", "df_cluster")))


def main():
    catalog = load_catalog()
    print(f"catalog: {len(catalog['objects'])} objects, built {catalog.get('generated')}")

    test_catalog_covers_every_target(catalog)
    test_zenith_cap()
    test_no_target_twice_at_once()
    test_dome_matching_and_portable_variety()
    test_never_hard_fails()
    test_contended_object_is_not_double_booked()
    test_slot_recommendation()
    test_quotas_and_back_compat()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
