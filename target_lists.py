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
    "HIP36850": "Castor"
}