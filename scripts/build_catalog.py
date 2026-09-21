#!/usr/bin/env python3
"""Resolve every deep-sky target once and cache the coordinates for the web app.

The browser cannot query SIMBAD (astroquery is not available under Pyodide, and
SIMBAD does not serve cross-origin requests anyway). Deep-sky coordinates never
change, so we look them up here and commit the result; the page loads it and
calls code.register_coordinates(). Planets and the Moon are computed live from
astropy's built-in ephemeris, so they are not in here.

Run this after adding targets to target_lists.py:

    python scripts/build_catalog.py

Anything SIMBAD cannot resolve is reported and left out, so it will fail loudly
in the app rather than silently going missing.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from code import resolve_objects
from target_lists import OBJECT_CLASSES, TELESCOPE_MODELS

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "web", "catalog.json")


def all_deep_sky_names():
    """Every non-solar-system target across all telescopes, de-duplicated."""
    names = set()
    for spec in TELESCOPE_MODELS.values():
        for cls in OBJECT_CLASSES:
            if cls == "planet":
                continue
            names.update(spec["targets"].get(cls, []))
    return sorted(names)


def main():
    names = all_deep_sky_names()
    print(f"Resolving {len(names)} deep-sky targets via SIMBAD...")

    coords = resolve_objects(names)

    missing = [n for n in names if n not in coords]
    if missing:
        print(f"\nWARNING: could not resolve {len(missing)}: {', '.join(missing)}")
        print("These will be unavailable in the web app until SIMBAD resolves them.")

    catalog = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "SIMBAD via astroquery",
        "objects": {
            name: {"ra": round(float(c.ra.deg), 6), "dec": round(float(c.dec.deg), 6)}
            for name, c in sorted(coords.items())
        },
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(catalog, f, indent=1, sort_keys=True)
        f.write("\n")

    print(f"\nWrote {len(catalog['objects'])} objects to {os.path.relpath(OUTPUT)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
