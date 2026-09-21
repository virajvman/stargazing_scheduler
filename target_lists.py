"""Dictionaries containing target lists and types for each of the telescopes we have at the observatory.
Catalog numbers: order by alphabetical, then numerical
Solar-system objects: order by distance from the Sun
"""

#useful link: http://www.waloszek.de/astro_us_evscope_messier_e.php
#http://www.waloszek.de/astro_us_evscope_gallery_2_e.php
#http://www.waloszek.de/astro_beob_ev2_e.php

objects_24inch: dict[str, str | list[str]] = {"cluster": ["M2", "M3", "M11", "M15", "M44", "M45", "NGC457", "NGC869"],
                  "galaxy": [],
                  "nebula": ["M42", "M57"],
                  "planet": ["jupiter", "saturn"],
                  "point": [],
                  "telescope_type": "24inch",
                 }


objects_07m: dict[str, str | list[str]] = {"cluster": ["M3", "M15", "M92"],
               "galaxy": ["M33", "M51", "M101", "NGC6946"],
               "nebula": ["M1", "M8", "M16", "M27", "M42", "M57"],
               "planet": ["mars", "jupiter", "saturn", "uranus", "neptune"],
               "point": [],
               "telescope_type": "07m",
              }

objects_ev: dict[str, str | list[str]] = {"cluster": ["M2", "M3", "M5", "M10", "M11", "M13", "M15", "M19", "M22", "M37", "M45", "M52", "M53", "M92", "NGC457", "NGC5466", "NGC5897"],
              "galaxy": ["M31", "M33", "M51", "M60", "M63", "M64", "M65", "M81", "M82", "M84", "M101", "M104", "M109", "NGC2903", "NGC4631"],
              "nebula": ["M8", "M16", "M17", "M20", "M27", "M42", "M57", "M97", "NGC2024", "NGC6543", "NGC7023", "NGC7662"],
              "planet": ["moon", "jupiter", "saturn"],
              "point": [],
              "telescope_type": "evscope",
             }

objects_5SE: dict[str, str | list[str]] = {"cluster": ["M5", "M13", "M15", "M45", "M92", "NGC457"],
               "nebula": ["M27", "M42", "M57", "NGC6543"],
               "galaxy": [],
               "point": ["HIP50583", "HIP65378", "HIP91919", "HIP92728", "HIP95947"],
               "planet": ["venus", "moon", "mars", "jupiter", "saturn"],
               "telescope_type": "5SE",
              }


objects_10Dob: dict[str, str | list[str]] = {"cluster": ["M45"],
                 "nebula": ["M42"],
                 "galaxy": [],
                 "point": ["HIP26549", "HIP36850", "HIP50583", "HIP65378", "HIP91919", "HIP92728", "HIP95947"],
                 "planet": ["venus", "moon", "mars", "jupiter", "saturn"],
                 "telescope_type": "10Dob",
                }


#### OBJECT TYPE INFO

cluster_types: dict[str, list[str]] = {
    "Open Cluster": ["M11", "M52", "M37", "M45", "M44", "NGC869", "NGC457"],
    "Globular Cluster": ["M15", "M13", "M92", "M5", "M3", "M2", "M10", "M53", "NGC5897", "NGC5466", "M19", "M22"],
}

cluster_type_mapping = {
    name: ctype
    for ctype, names in cluster_types.items()
    for name in names
}


outreach_link: dict[str, str] = {
    "Open Cluster": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.fdkwv3g7vf4i",
    "Globular Cluster": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.7ctyu5s0fb9n",
    "galaxy": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.gvsja0wbdv2f",
    "planet": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.pdu2bqr8e9z9",
    "nebula": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.hfgmj1uho9ly",
}

common_name: dict[str, str] = {
    "M1": "Crab Nebula",
    "M8": "Lagoon Nebula",
    "M11": "Wild Duck Cluster",
    "M13": "Hercules Cluster",
    "M15": "Great Pegasus Cluster",
    "M16": "Eagle Nebula",
    "M17": "Omega/Swan Nebula",
    "M20": "Trifid Nebula",
    "M27": "Dumbbell Nebula",
    "M31": "Andromeda Galaxy",
    "M33": "Triangulum Galaxy",
    "M42": "Orion Nebula",
    "M44": "Beehive Cluster",
    "M45": "Pleiades",
    "M57": "Ring Nebula",
    "M63": "Sunflower Galaxy",
    "M64": "Black Eye Galaxy",
    "M81": "Bode's Galaxy",
    "M82": "Cigar Galaxy",
    "M97": "Owl Nebula",
    "M101": "Pinwheel Galaxy",
    "M104": "Sombrero Galaxy",
    "NGC457": "Owl/Dragonfly cluster",
    "NGC869": "Double Cluster",
    "NGC2024": "Flame Nebula",
    "NGC4631": "Whale Galaxy",
    "NGC5466": "Snowglobe Cluster",
    "NGC5897": "Ghost Cluster",
    "NGC6543": "Cat's Eye Nebula",
    "NGC6819": "Foxhead/Octopus Cluster",
    "NGC6946": "Fireworks Galaxy",
    "NGC7000": "North America Nebula",
    "NGC7023": "Iris Nebula",
    "NGC7662": "Blue Snowball Nebula",
    "HIP26549": "Sigma-Orionis",
    "HIP36850": "Castor",
    "HIP91919": "Epsilon Lyrae",
    "HIP92728": "Delta1 Lyrae",
    "HIP95947": "Albireo",
}


#Per-object outreach links, which beat the per-category ones in `outreach_link`
#when present. Harvested from the spreadsheet the observatory already shares, so
#the exported sheet needs no hand-editing for these. Anything not listed falls
#back to the category link, so adding entries here is purely an improvement.
outreach_link_by_object: dict[str, str] = {
    "HIP91919": "https://en.wikipedia.org/wiki/Epsilon_Lyrae",
    "HIP92728": "https://en.wikipedia.org/wiki/Delta1_Lyrae",
    "HIP95947": "https://en.wikipedia.org/wiki/Albireo",
    "M2": "https://www.youtube.com/watch?v=Ae2_AILda-w",
    "M3": "https://www.youtube.com/watch?v=tl836xXiNj4",
    "M11": "https://www.youtube.com/watch?v=8ye5hCcGM5Q",
    "M13": "https://www.youtube.com/watch?v=HISG5N04P2A",
    "M15": "https://www.youtube.com/watch?v=S-vLAg3bNDk",
    "M27": "https://www.youtube.com/watch?v=uP6eChP7i44",
    "M51": "https://www.youtube.com/watch?v=yiv6a8BVzPE",
    "M57": "https://www.youtube.com/watch?v=_TovLkVHfZE",
    "M63": "https://www.youtube.com/watch?v=S0N98fMLkbU",
    "M92": "https://www.youtube.com/watch?v=hjaGzXz6dWw",
    "M101": "https://www.youtube.com/watch?v=flxa5hJV7OA",
    "NGC5466": "https://en.wikipedia.org/wiki/NGC_5466",
    "NGC6543": "https://www.youtube.com/watch?v=zvRmTaEjXPQ",
    "NGC6946": "https://en.wikipedia.org/wiki/NGC_6946",
    "NGC7023": "https://www.youtube.com/watch?v=aNJgQlJDPMY",
}

#the 8-inch and the 10-inch Dob get pointed at the same things, so they share one
#list. Give the 8-inch its own dict here if the two ever diverge.
objects_8inch: dict[str, str | list[str]] = dict(objects_10Dob, telescope_type="8inch")


#### TELESCOPE REGISTRY

"""The telescopes we can put on the lawn, and how visitors move between them.

A *model* is a kind of telescope; an *instance* is one of them on a given night.
Some nights there are two Dobs, some nights one, so the roster is built at
schedule time from a {model: count} dict via build_roster().

`kind` drives the default category coupling (see code.schedule_group). Both
default to "diverse" -- different categories at the same time -- for opposite
reasons:

  "portable" -> visitors walk the whole portable line in one go, so showing
                different categories at once gives them maximum variety in the
                few minutes they spend at the tables.
  "dome"     -> the two domes are different instruments: the 24-inch is an
                eyepiece, the 0.7 m takes long exposures, so they are good at
                different things and their lists reflect that (the 24-inch owns
                no galaxies). Keeping them apart lets each play to its strength,
                and a visitor who catches one dome and later the other still sees
                variety -- measurably more of it than when the domes are forced
                to match, because matching confines both to the narrow overlap
                between their lists. See the note in code.schedule_group.

Variety for a visitor who stays at one dome comes from
code.SEQUENCE_VARIETY_PENALTY, which keeps a telescope from showing the same
category twice in a row.

`max_altitude` caps how close to the zenith a telescope will be pointed. The
eVscopes track poorly overhead, so they stop at 80 deg.

`minutes_per_target` is how long one object realistically takes at that
telescope, counting re-pointing and letting a queue of people look. It is only
used to suggest how many targets to schedule (code.recommend_slots), so adjust it
if a night feels rushed or draggy -- nothing else depends on it.
"""

ZENITH_LIMIT_EVSCOPE = 80.0

TELESCOPE_MODELS: dict[str, dict] = {
    "24inch": {
        "display": '24-inch Dome',
        "sheet_title": "24-inch",
        "kind": "dome",
        "minutes_per_target": 30,  # a queue of visitors filing past one eyepiece
        "targets": objects_24inch,
        "max_altitude": None,
        "max_count": 1,
        "default_count": 1,
    },
    "07m": {
        "display": "0.7 m Dome",
        "sheet_title": "0.7m",
        "kind": "dome",
        "minutes_per_target": 25,  # same, but quicker to re-point
        "targets": objects_07m,
        "max_altitude": None,
        "max_count": 1,
        "default_count": 1,
    },
    "evscope": {
        "display": "eVscope",
        "sheet_title": "eVscope",
        "kind": "portable",
        "minutes_per_target": 15,  # automated, and variety is the whole point here
        "targets": objects_ev,
        "max_altitude": ZENITH_LIMIT_EVSCOPE,
        "max_count": 4,
        "default_count": 2,
    },
    "5SE": {
        "display": "Celestron 5SE",
        "sheet_title": "5SE",
        "kind": "portable",
        "minutes_per_target": 20,  # manual pointing, visual
        "targets": objects_5SE,
        "max_altitude": None,
        "max_count": 2,
        "default_count": 1,
    },
    "10Dob": {
        "display": '10-inch Dobsonian',
        "sheet_title": "10-inch Dob",
        "kind": "portable",
        "minutes_per_target": 20,  # manual pointing, visual
        "targets": objects_10Dob,
        "max_altitude": None,
        "max_count": 3,
        "default_count": 1,
    },
    "8inch": {
        "display": '8-inch',
        "sheet_title": "8-inch",
        "kind": "portable",
        "minutes_per_target": 20,  # manual pointing, visual
        "targets": objects_8inch,
        "max_altitude": None,
        "max_count": 2,
        "default_count": 0,
    },
}

#the object classes we schedule, and that get coupled between telescopes
OBJECT_CLASSES: list[str] = ["cluster", "nebula", "galaxy", "planet", "point"]

#human-readable class names, used in the web UI and the printed tables
CLASS_DISPLAY: dict[str, str] = {
    "cluster": "Star Clusters",
    "nebula": "Nebulae",
    "galaxy": "Galaxies",
    "planet": "Planets & Moon",
    "point": "Stars & Multiple Systems",
}


def instance_labels(model: str, count: int) -> list[str]:
    """Output labels for `count` copies of `model`.

    One of a kind keeps the bare model name ("5SE"); two or more get numbered
    ("evscope_1", "evscope_2"), which is what the existing catalog_*.csv files
    are already named.
    """
    if count <= 0:
        return []
    if count == 1:
        return [model]
    return [f"{model}_{i + 1}" for i in range(count)]


def build_roster(counts: dict[str, int] | None = None) -> list[dict]:
    """Expand a {model: how many tonight} dict into a list of telescope instances.

    Each instance is what code.schedule_group consumes:
        {"label", "display", "model", "kind", "targets", "max_altitude"}

    Passing None uses each model's default_count, i.e. the usual observatory
    setup: both domes, two eVscopes, a 5SE and one 10-inch Dob.
    """
    if counts is None:
        counts = {m: spec["default_count"] for m, spec in TELESCOPE_MODELS.items()}

    roster = []
    for model, spec in TELESCOPE_MODELS.items():
        n = int(counts.get(model, 0))
        if n < 0:
            raise ValueError(f"Cannot have {n} of the {model}")
        if n > spec["max_count"]:
            raise ValueError(
                f"Only {spec['max_count']} of the {model} exist(s), got {n}"
            )
        labels = instance_labels(model, n)
        for i, label in enumerate(labels):
            roster.append({
                "label": label,
                "display": spec["display"] if n == 1 else f"{spec['display']} #{i + 1}",
                "model": model,
                "kind": spec["kind"],
                "targets": spec["targets"],
                "max_altitude": spec["max_altitude"],
                "minutes_per_target": spec["minutes_per_target"],
                "sheet_title": (spec["sheet_title"] if n == 1
                                else f"{spec['sheet_title']} {i + 1}"),
            })
    return roster


def default_groups(roster: list[dict] | None = None) -> list[dict]:
    """Split a roster into the two coupled groups, each kept varied within itself."""
    if roster is None:
        roster = build_roster()

    groups = []
    dome = [t["label"] for t in roster if t["kind"] == "dome"]
    portable = [t["label"] for t in roster if t["kind"] == "portable"]
    if dome:
        groups.append({"name": "Dome telescopes", "telescopes": dome, "coupling": "diverse"})
    if portable:
        groups.append({"name": "Portable telescopes", "telescopes": portable, "coupling": "diverse"})
    return groups
