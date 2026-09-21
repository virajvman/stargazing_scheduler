#!/usr/bin/env python3
"""Checks for the three telescopes-at-once rules.

Runs without pytest and without SIMBAD (it reads the committed coordinate
catalog), so it is safe to run anywhere:

    python tests/test_scheduling.py
"""

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import code as sched
import spreadsheet
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


def test_groups_stay_varied():
    print("\nrules 2 and 3: each group shows different categories at once")
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

    hit, tot = stats["diverse"]
    print(f"        telescopes on distinct categories in {hit}/{tot} slots")

    #Perfect compliance is impossible: a group with more telescopes than
    #categories up tonight must overlap. The threshold guards a regression.
    check("groups stay varied in most slots", tot and hit / tot >= 0.80, f"{hit}/{tot}")

    #and the coupling must be doing the work, not luck
    loose = [dict(g, coupling="none") for g in T.default_groups(T.build_roster())]
    none_hit = none_tot = 0
    for date in DATES:
        out = sched.schedule_night(date, "20:00", "22:00", roster=T.build_roster(),
                                   groups=loose, verbose=False)
        for g in out["groups"]:
            per = {l: rows_of(out, l) for l in g["telescopes"]}
            if len(per) < 2:
                continue
            n = min(len(v) for v in per.values())
            for k in range(n):
                classes = [per[l][k]["type"] for l in g["telescopes"]]
                none_hit += len(set(classes)) == len(classes)
                none_tot += 1
    print(f"        with coupling off, that would be {none_hit}/{none_tot}")
    check("coupling beats no coupling", hit / tot > none_hit / none_tot,
          f"coupled {hit}/{tot} vs uncoupled {none_hit}/{none_tot}")


def test_dome_visitor_sees_variety():
    """The point of the dome rule: one dome now, the other later, not the same thing.

    This is the metric the dome setting is actually chosen on, so it is what the
    test guards -- not whether the domes happen to match each other.
    """
    print("\na visitor who sees one dome, then the other later")
    domes = [t["label"] for t in T.build_roster() if t["kind"] == "dome"]
    if len(domes) < 2:
        return

    same = same_n = 0
    for date, out in nights():
        a = [r["type"] for r in rows_of(out, domes[0])]
        b = [r["type"] for r in rows_of(out, domes[1])]
        for t1 in range(len(a)):
            for t2 in range(len(b)):
                if t1 == t2:
                    continue
                same_n += 1
                same += a[t1] == b[t2]

    rate = 100 * same / same_n
    print(f"        lands on the same category {rate:.0f}% of the time")
    #~25-33% is what chance alone would give, and forcing the domes to match
    #measured 26%. Anything at or above that means the setting stopped helping.
    check("a dome visitor rarely sees a repeated category", rate <= 22.0,
          f"{rate:.0f}% --- at or above chance, so the dome coupling is not helping")

    #the 0.7 m is the only dome that can do galaxies; it should be using that
    gal = gal_n = 0
    for date, out in nights():
        seq = [r["type"] for r in rows_of(out, "07m")]
        gal_n += len(seq)
        gal += seq.count("galaxy")
    share = 100 * gal / gal_n
    print(f"        the 0.7 m spends {share:.0f}% of its slots on galaxies")
    check("the long-exposure dome still gets to do galaxies", share >= 35.0,
          f"{share:.0f}% --- matching the domes drops this to ~12%")


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


def test_combined_workbook():
    """The .xlsx we hand round: valid zip, well-formed XML, right shape."""
    print("\ncombined spreadsheet")
    import xml.etree.ElementTree as ET
    import zipfile as zf_mod

    roster = T.build_roster({"24inch": 1, "07m": 1, "evscope": 2})
    out = sched.schedule_night("2026-08-03", "21:15", "22:45", roster=roster,
                               verbose=False)

    sections = []
    for g in out["groups"]:
        for label in g["telescopes"]:
            res = out["telescopes"][label]
            inst = next(t for t in roster if t["label"] == label)
            frame = sched.build_catalog_frames(
                res["schedule"], "2026-08-03", df_alternates=res["alternates"])[0]
            sections.append((inst["sheet_title"], frame))

    data = spreadsheet.write_xlsx(spreadsheet.combined_sheet(sections))

    check("starts with the zip magic bytes", data[:4] == b"PK\x03\x04")

    try:
        zf = zf_mod.ZipFile(io.BytesIO(data))
    except Exception as exc:
        check("is a readable zip", False, str(exc))
        return

    needed = ["[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
              "xl/_rels/workbook.xml.rels", "xl/styles.xml",
              "xl/worksheets/sheet1.xml", "xl/worksheets/_rels/sheet1.xml.rels"]
    missing = [n for n in needed if n not in zf.namelist()]
    check("holds every part a reader needs", not missing, f"missing {missing}")

    bad = []
    for name in zf.namelist():
        try:
            ET.fromstring(zf.read(name))
        except ET.ParseError as exc:
            bad.append(f"{name}: {exc}")
    check("every part is well-formed XML", not bad, "; ".join(bad))

    sheet = zf.read("xl/worksheets/sheet1.xml").decode()
    for title, _ in sections:
        if f"<t>{title}</t>" not in sheet:
            check(f"section {title!r} is present", False, "title row missing")
            break
    else:
        check("every telescope gets its own titled section", True)

    #hyperlink ids in the sheet must all resolve in its rels part
    rels = zf.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
    ids = set(re.findall(r'<hyperlink ref="[^"]+" r:id="(rId\d+)"/>', sheet))
    defined = set(re.findall(r'Id="(rId\d+)"', rels))
    check("every hyperlink resolves to a target", ids and ids <= defined,
          f"{len(ids)} links, {len(ids - defined)} dangling")

    #ampersands in YouTube URLs are the classic way to produce broken XML
    check("URLs with & are escaped", "&amp;" in rels or "&" not in rels,
          "raw ampersand in the rels part")

    #elevations stay numeric so the column can be sorted in Sheets
    check("elevation is written as a number",
          re.search(r'<c r="C\d+"><v>\d', sheet) is not None)


def test_interval_has_meridian():
    print("\ninterval labels")
    import pandas as pd
    a = pd.to_datetime("2026-08-03 21:15")
    b = pd.to_datetime("2026-08-03 21:45")
    check("reads like the shared sheet", sched.interval_to_str(a, b) == "9:15-9:45pm",
          sched.interval_to_str(a, b))

    a = pd.to_datetime("2026-08-03 23:45")
    b = pd.to_datetime("2026-08-04 00:15")
    check("both meridians when it crosses midnight",
          sched.interval_to_str(a, b) == "11:45pm-12:15am", sched.interval_to_str(a, b))


def test_per_object_outreach_links():
    print("\noutreach links")
    roster = T.build_roster({"07m": 1})
    out = sched.schedule_night("2026-08-03", "21:15", "22:45", roster=roster,
                               verbose=False)
    frame = out["telescopes"]["07m"]["catalog"]

    rows = frame[frame["Catalog Name"].isin(T.outreach_link_by_object)]
    if len(rows) == 0:
        print("        (no objects with a specific link were scheduled)")
        return
    wrong = [r["Catalog Name"] for _, r in rows.iterrows()
             if r["Outreach Info"] != T.outreach_link_by_object[r["Catalog Name"]]]
    check("an object's own link beats its category link", not wrong, str(wrong))

    #and everything else still gets the category link rather than a blank
    others = frame[(~frame["Catalog Name"].isin(T.outreach_link_by_object))
                   & (frame["Object Type"].isin(["galaxy", "nebula", "planet",
                                                 "Open Cluster", "Globular Cluster"]))]
    blank = [r["Catalog Name"] for _, r in others.iterrows() if not r["Outreach Info"]]
    check("objects without one fall back to the category link", not blank, str(blank))


def main():
    catalog = load_catalog()
    print(f"catalog: {len(catalog['objects'])} objects, built {catalog.get('generated')}")

    test_catalog_covers_every_target(catalog)
    test_zenith_cap()
    test_no_target_twice_at_once()
    test_groups_stay_varied()
    test_dome_visitor_sees_variety()
    test_never_hard_fails()
    test_contended_object_is_not_double_booked()
    test_slot_recommendation()
    test_quotas_and_back_compat()
    test_interval_has_meridian()
    test_per_object_outreach_links()
    test_combined_workbook()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
