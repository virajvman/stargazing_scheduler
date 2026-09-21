"""Glue between the web page and the scheduler.

Runs inside Pyodide. The page hands in a JSON config, gets back JSON that is
ready to render, so the scheduling logic stays in code.py and is never
reimplemented in JavaScript.
"""

import base64
import io
import json
import zipfile

import spreadsheet
import stargazing as sched
from target_lists import (TELESCOPE_MODELS, OBJECT_CLASSES, CLASS_DISPLAY,
                          cluster_type_mapping, common_name, build_roster)


def describe_models():
    """Everything the page needs to draw the telescope picker."""
    models = []
    for name, spec in TELESCOPE_MODELS.items():
        counts = {cls: len(spec["targets"].get(cls, [])) for cls in OBJECT_CLASSES}
        models.append({
            "model": name,
            "display": spec["display"],
            "kind": spec["kind"],
            "max_altitude": spec["max_altitude"],
            "max_count": spec["max_count"],
            "default_count": spec["default_count"],
            "target_counts": counts,
            "total_targets": sum(counts.values()),
        })
    return {
        "models": models,
        "classes": [{"key": c, "display": CLASS_DISPLAY[c]} for c in OBJECT_CLASSES],
    }


def _display_name(catalog_name):
    return common_name.get(catalog_name, catalog_name)


def _object_type(catalog_name, cls):
    if cls == "cluster":
        return cluster_type_mapping.get(catalog_name, "Star Cluster")
    return CLASS_DISPLAY.get(cls, cls)


#formatted tables from the last run, so the workbook download needs no rerun
_FRAMES = {}


def run_schedule(config_json):
    """Schedule a night. Returns a JSON string; never raises."""
    try:
        cfg = json.loads(config_json)
        return json.dumps(_run(cfg))
    except Exception as exc:  # surfaced in the page's error banner
        return json.dumps({"ok": False, "error": str(exc)})


def _run(cfg):
    _FRAMES.clear()

    #per-telescope category counts, e.g. {"07m": {"galaxy": 2}}
    quotas = {}
    for label, wanted in (cfg.get("quotas") or {}).items():
        clean = {c: int(n) for c, n in wanted.items() if n is not None and str(n) != ""}
        if clean:
            quotas[label] = clean

    counts = {m: int(n) for m, n in cfg.get("counts", {}).items()}
    roster = build_roster(counts)
    if not roster:
        return {"ok": False, "error": "No telescopes selected."}

    by_label = {t["label"]: t for t in roster}

    #the page sends its own groups so the operator can regroup telescopes
    groups = []
    for g in cfg.get("groups", []):
        labels = [l for l in g["telescopes"] if l in by_label]
        if labels:
            groups.append({"name": g["name"], "telescopes": labels,
                           "coupling": g.get("coupling", "none")})
    if not groups:
        return {"ok": False, "error": "No telescope groups to schedule."}

    #a group with no explicit count gets one recommended for it
    slots_by_group = {g["name"]: int(g["num_slots"]) for g in cfg.get("groups", [])
                      if g.get("num_slots")}

    out = sched.schedule_night(
        cfg["date"], cfg["start_time"], cfg["end_time"],
        groups=groups,
        roster=roster,
        num_slots=None,
        slots_by_group=slots_by_group,
        quotas_by_telescope=quotas or None,
        min_altitude=float(cfg.get("min_altitude", 30)),
        num_alternates=int(cfg.get("num_alternates", 3)),
        write_csv=False,
        verbose=False,
    )

    payload = {
        "ok": True,
        "date": out["date"],
        "start_time": out["start_time"],
        "end_time": out["end_time"],
        "min_altitude": float(cfg.get("min_altitude", 30)),
        "groups": [],
        "telescopes": {},
    }

    for g in out["groups"]:
        payload["groups"].append(g)
        for label in g["telescopes"]:
            res = out["telescopes"][label]
            inst = by_label[label]
            df = res["schedule"]

            rows = []
            for _, r in df.iterrows():
                if r["object"] is None:
                    #a slot nothing could fill; kept so the group stays aligned
                    rows.append({
                        "object": None,
                        "start": sched.dt_to_timestr(r["start"]),
                        "end": sched.dt_to_timestr(r["end"]),
                    })
                    continue
                #altitude across the slot, for the page's click-to-inspect chart
                track = [
                    {"t": sched.dt_to_timestr(ts), "alt": float(a)}
                    for ts, a in zip(r.get("track_times", []), r.get("track", []))
                ]

                rows.append({
                    "object": r["object"],
                    "name": _display_name(r["object"]),
                    "cls": r["type"],
                    "type": _object_type(r["object"], r["type"]),
                    "elev": int(r["elev"]),
                    "path": r["path"],
                    "repeat": bool(r.get("repeat", False)),
                    "start": sched.dt_to_timestr(r["start"]),
                    "end": sched.dt_to_timestr(r["end"]),
                    "track": track,
                })

            alternates = []
            for _, r in res["alternates"].iterrows():
                alternates.append({
                    "object": r["object"],
                    "name": _display_name(r["object"]),
                    "cls": r["type"],
                    "type": _object_type(r["object"], r["type"]),
                    "elev": int(r["elev"]),
                    "when": ("earlier in the night" if r["path"] == "falling"
                             else "later at night"),
                })

            observable = {cls: int(len(res["observable"][cls])) for cls in OBJECT_CLASSES}

            payload["telescopes"][label] = {
                "label": label,
                "sheet_title": inst["sheet_title"],
                "notes": res["notes"],
                "display": res["display"],
                "model": inst["model"],
                "kind": inst["kind"],
                "group": g["name"],
                "max_altitude": inst["max_altitude"],
                "rows": rows,
                "alternates": alternates,
                "observable": observable,
                "csv": res["csv"],
            }

            #the exact table that goes in the CSV and the combined sheet
            _FRAMES[label] = sched.build_catalog_frames(
                res["schedule"], cfg["date"], df_alternates=res["alternates"])[0]

    payload["checks"] = _coupling_report(payload)

    return payload


def _coupling_report(payload):
    """Did the category rules actually hold? Shown in the page so it is checkable."""
    report = []
    for g in payload["groups"]:
        labels = g["telescopes"]
        if len(labels) < 2:
            continue

        n = min(len(payload["telescopes"][l]["rows"]) for l in labels)

        #With more telescopes than categories in the sky, "every telescope on a
        #different category" is arithmetically impossible, so score against the
        #best a night allows rather than against len(labels) -- otherwise adding a
        #sixth portable makes a perfectly good schedule report zero.
        reachable = set()
        for l in labels:
            reachable |= {c for c, cnt in payload["telescopes"][l]["observable"].items()
                          if cnt > 0}
        best_possible = min(len(labels), len(reachable)) if reachable else 1

        matched = 0
        counted = 0
        for k in range(n):
            classes = [payload["telescopes"][l]["rows"][k].get("cls") for l in labels]
            if any(c is None for c in classes):
                #an empty slot cannot match or differ from anything
                continue
            counted += 1
            distinct = len(set(classes))
            if g["coupling"] == "match":
                matched += 1 if distinct == 1 else 0
            elif g["coupling"] == "diverse":
                matched += 1 if distinct >= best_possible else 0

        if g["coupling"] == "match":
            goal = "all telescopes on the same category"
        elif g["coupling"] == "diverse":
            goal = ("every telescope on a different category" if best_possible >= len(labels)
                    else f"as many different categories as the sky allows ({best_possible})")
        else:
            continue

        report.append({
            "group": g["name"],
            "coupling": g["coupling"],
            "goal": goal,
            "achieved": matched,
            "total": counted,
            "blockers": _blockers(payload, g) if matched < counted else [],
        })
    return report


def _blockers(payload, g):
    """Why a group could not follow its rule, in terms the operator can act on.

    A matched group is capped by the *narrowest* list in it: a telescope with no
    galaxies up tonight can never match a partner that is on one. A varied group
    is capped the other way, by having more telescopes than categories to spread
    across.
    """
    labels = g["telescopes"]
    reachable = {l: {c for c, n in payload["telescopes"][l]["observable"].items() if n > 0}
                 for l in labels}

    reasons = []

    if g["coupling"] == "match":
        shared = set.intersection(*reachable.values()) if reachable else set()
        for label in labels:
            missing = sorted(set.union(*reachable.values()) - reachable[label])
            if missing:
                names = ", ".join(CLASS_DISPLAY[c].lower() for c in missing)
                reasons.append(
                    f"{payload['telescopes'][label]['display']} has no {names} up "
                    f"tonight, so it cannot match a partner showing one"
                )
        if len(shared) == 0:
            reasons.append(
                "the telescopes have no category in common tonight, so they cannot match at all"
            )
        elif len(shared) == 1:
            reasons.append(
                "the telescopes share only one category tonight, so they must repeat it"
            )

    elif g["coupling"] == "diverse":
        spread = len(set.union(*reachable.values())) if reachable else 0
        if spread < len(labels):
            reasons.append(
                f"{len(labels)} telescopes but only {spread} categor"
                f"{'y' if spread == 1 else 'ies'} up tonight, so some must overlap"
            )

    return reasons


def zip_bundle(result_json):
    """Bundle every telescope's CSV into one zip, returned base64 for download."""
    data = json.loads(result_json)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, tel in data["telescopes"].items():
            zf.writestr(f"catalog_{label}.csv", tel["csv"])
    return base64.b64encode(buf.getvalue()).decode("ascii")


def workbook_bundle(result_json):
    """Every telescope down one sheet, as .xlsx, base64 for download.

    This is the sheet that gets shared: import it straight into Google Sheets.
    """
    data = json.loads(result_json)

    #keep the on-screen order: group by group, telescope by telescope
    sections = []
    for group in data["groups"]:
        for label in group["telescopes"]:
            frame = _FRAMES.get(label)
            if frame is None:
                continue
            title = data["telescopes"][label].get("sheet_title", label)
            sections.append((title, frame))

    if not sections:
        raise RuntimeError("Nothing to export -- make a schedule first.")

    sheet = spreadsheet.combined_sheet(sections, sheet_name="Schedule")
    return base64.b64encode(spreadsheet.write_xlsx(sheet)).decode("ascii")
