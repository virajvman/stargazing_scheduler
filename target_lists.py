#useful link: http://www.waloszek.de/astro_us_evscope_messier_e.php
#http://www.waloszek.de/astro_us_evscope_gallery_2_e.php
#http://www.waloszek.de/astro_beob_ev2_e.php

objects_24inch = {"cluster":["M15", "M3", "M2", "M11", "M44", "NGC457", "M45","NGC869"],
                  "galaxy":[],
                  "nebula":["M57","M42"],
                  "planet":["saturn", "jupiter"],
                  "point":[],
                  "telescope_type": "24inch"
                 }


objects_07m = {"cluster": ["M15", "M92"],
              "galaxy":["M51", "M33", "NGC6946", "M101"],
              "nebula":["M16", "M8", "M57", "M27", "M1", "M42"],
              "planet":["mars", "jupiter", "saturn", "uranus", "neptune"],
              "point":[],
            "telescope_type": "07m"
              }

objects_ev = {"cluster":["M15", "M13", "M92", "M5", "M3", "M2", "M10", "M53", "NGC5897", "NGC5466", "NGC457","M19","M22","M11","M52","M37","M45"],
             "galaxy":["M101", "M33", "M31", "M81", "M51", "M64", "M82", "M104","M109", "M65","M63","M84","NGC2903"],
             "nebula": ["NGC6543", "M57", "M27", "M42","NGC2024","M8","M16","M17","M20","NGC7023","M97"],
             "planet": ["jupiter","saturn"],
             "point":[],
            "telescope_type": "evscope"

             }

objects_5SE = {"cluster":["M45","NGC457"],
               "nebula":["M42","M57"],
               "galaxy":[],
               "point":["HIP91919","HIP92728", "HIP50583", "HIP65378", "HIP95947"],
               "planet":["venus","mars","jupiter","saturn","moon"],
                "telescope_type": "5SE"
               }


objects_10Dob = {"cluster":["M45"],
                "nebula":["M42"],
                "galaxy":[],
                "point":["HIP91919", "HIP92728", "HIP50583", "HIP65378", "HIP95947", "HIP26549", "HIP36850"],
                "planet":["moon", "venus", "mars", "saturn", "jupiter"],
                "telescope_type":"10Dob"
}


#### OBJECT TYPE INFO

cluster_types = {
    "Open Cluster": ["M11","M52","M37","M45", "M44", "NGC869","NGC457"],
    "Globular Cluster": ["M15","M13","M92","M5","M3","M2","M10","M53","NGC5897","NGC5466","M19","M22"]
}

cluster_type_mapping = {
    name: ctype
    for ctype, names in cluster_types.items()
    for name in names
}


outreach_link = {
    "Open Cluster": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.fdkwv3g7vf4i" ,
    "Globular Cluster": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.7ctyu5s0fb9n",
    "galaxy": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.gvsja0wbdv2f",
    "planet": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.pdu2bqr8e9z9",
    "nebula": "https://docs.google.com/document/d/1gFdZzrRGJdO8h30Y4WZMfgOvV_Y-Xj6xaUKWY6pTceE/edit?tab=t.0#heading=h.hfgmj1uho9ly",
}

common_name = {
    "M45":"Pleiades",
    "M44": "Beehive Cluster",
    "NGC869": "Double Cluster",
    "M42": "Orion Nebula",
    "NGC6946": "Firework's Galaxy",
    "M33": "Triangulum Galaxy",
    "M1": "Crab Nebula",
    "NGC457": "Owl/Dragonfly cluster",
    "NGC7023": "Iris Nebula",
    "M82": "Cigar Galaxy",
    "M31": "Andromeda Galaxy",
    "NGC2024": "Flame Nebula",
    "M81":"Bode's Galaxy",
    "HIP26549": "Sigma-Orionis",
    "HIP36850": "Castor"
}