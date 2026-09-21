import itertools
import os
import numpy as np
import pandas as pd
import time
from datetime import timedelta

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from astropy.coordinates import EarthLocation, AltAz, get_body
from target_lists import (common_name, outreach_link, cluster_type_mapping,
                          OBJECT_CLASSES, TELESCOPE_MODELS, build_roster, default_groups)
import pytz
from datetime import datetime

#astroquery is only needed to look up coordinates we have not cached yet. It is
#not available under Pyodide, so the web front end pre-loads a coordinate catalog
#(see register_coordinates) and never touches SIMBAD.
try:
    from astroquery.simbad import Simbad
except ImportError:  # pragma: no cover - depends on the environment
    Simbad = None

pacific = pytz.timezone("US/Pacific")

# Palo Alto, CA
palo_alto_location = EarthLocation(
    lat=37.4419 * u.deg,
    lon=-122.1430 * u.deg,
    height=90 * u.m # observatory height above sea level
)

#name -> SkyCoord for everything we have already looked up. Deep-sky coordinates
#never change, so this doubles as the offline catalog used in the browser.
_COORD_CACHE = {}


def register_coordinates(coords_deg):
    """
    Pre-load object coordinates so no SIMBAD query is needed.

    coords_deg : dict of name -> (ra_deg, dec_deg), or name -> {"ra": .., "dec": ..}

    Used by the web front end, which ships a generated coordinate catalog
    (scripts/build_catalog.py writes it). Also worth calling in a notebook to
    avoid hammering SIMBAD on every re-run.
    """
    for name, value in coords_deg.items():
        if isinstance(value, dict):
            ra, dec = value["ra"], value["dec"]
        else:
            ra, dec = value
        _COORD_CACHE[name] = SkyCoord(ra=float(ra) * u.deg, dec=float(dec) * u.deg,
                                      frame="icrs")
    return len(_COORD_CACHE)


def altitude_in_band(altitudes, min_altitude, max_altitude=None):
    """
    Is the telescope allowed to point here?

    An object is usable while its altitude sits inside
    [min_altitude, max_altitude]. The upper limit is what keeps the eVscopes away
    from the zenith, where their mounts track badly -- note this is a band, not a
    rejection: a target that culminates overhead is still perfectly good earlier
    or later in the night, on its way up or down.

    Accepts a scalar or an array, and returns the same shape as a bool.
    """
    alts = np.asarray(altitudes, dtype=float)
    ok = alts >= min_altitude
    if max_altitude is not None:
        ok = ok & (alts <= max_altitude)
    return ok if ok.ndim else bool(ok)

def _is_simbad_transient_error(exc):
    """
    Heuristic: is this SIMBAD exception likely transient (network/capabilities/cache)?
    """
    msg = str(exc).lower()
    transient_markers = [
        "capabilities endpoint",
        "remote end closed",
        "connection aborted",
        "connection reset",
        "timed out",
        "timeout",
        "503",
        "502",
        "504",
        "temporarily unavailable",
    ]
    return any(m in msg for m in transient_markers)


def _try_clear_simbad_cache():
    """
    Try to clear the astroquery SIMBAD cache. Available in newer astroquery versions.
    Silently no-ops on older versions.
    """
    try:
        Simbad.clear_cache()
    except Exception:
        pass


def _is_masked_or_nan(value):
    """
    Detect masked/NaN values returned by SIMBAD for unresolvable names.
    """
    #Astropy masked constant
    try:
        from astropy.utils.masked import Masked  # type: ignore
        if isinstance(value, Masked) and getattr(value, "mask", False):
            return True
    except Exception:
        pass
    #numpy.ma masked element
    try:
        import numpy.ma as ma
        if value is ma.masked:
            return True
    except Exception:
        pass
    #NaN floats
    try:
        if isinstance(value, float) and np.isnan(value):
            return True
        farr = np.asarray(value, dtype=float)
        if farr.size == 1 and np.isnan(farr.item()):
            return True
    except Exception:
        pass
    return False


def _coord_from_simbad_row(row):
    """
    Build a SkyCoord from a SIMBAD result row, accepting either the new
    'ra'/'dec' (decimal degrees) columns or the legacy 'RA'/'DEC' sexagesimal columns.

    Raises ValueError if the row's RA/Dec is masked/NaN, so callers can treat
    that exactly like the original "could not resolve" case (name not added).
    """
    if "ra" in row.colnames and "dec" in row.colnames:
        ra_val = row["ra"]
        dec_val = row["dec"]
        if _is_masked_or_nan(ra_val) or _is_masked_or_nan(dec_val):
            raise ValueError("SIMBAD returned masked/NaN RA/Dec (unresolvable name)")
        return SkyCoord(ra=ra_val * u.deg, dec=dec_val * u.deg, frame="icrs")
    if "RA" in row.colnames and "DEC" in row.colnames:
        ra_val = row["RA"]
        dec_val = row["DEC"]
        if _is_masked_or_nan(ra_val) or _is_masked_or_nan(dec_val):
            raise ValueError("SIMBAD returned masked/NaN RA/Dec (unresolvable name)")
        return SkyCoord(ra=ra_val, dec=dec_val, unit=(u.hourangle, u.deg), frame="icrs")
    raise KeyError("SIMBAD result row has no recognized RA/Dec columns")


def resolve_objects(object_names, max_retries=3, retry_wait_s=2.0):
    """
    For extra-galactic objects.
    Resolve object names to SkyCoord using SIMBAD.

    Resilient to transient SIMBAD outages (e.g. "No working capabilities endpoint
    provided"): tries a single batched query first, then falls back to per-name
    queries with retries and cache-clearing.

    Returns dict: name -> SkyCoord
    """
    coords = {}
    if len(object_names) == 0:
        return coords

    #fastest path: anything already in the coordinate catalog needs no query
    unresolved = []
    for name in object_names:
        if name in _COORD_CACHE:
            coords[name] = _COORD_CACHE[name]
        else:
            unresolved.append(name)

    object_names = unresolved
    if len(object_names) == 0:
        return coords

    if Simbad is None:
        raise RuntimeError(
            "astroquery is unavailable and these objects are not in the coordinate "
            f"catalog: {sorted(object_names)}. Either install astroquery, or add them "
            "with scripts/build_catalog.py and call register_coordinates()."
        )

    #fast path: one batched call to SIMBAD instead of N
    for attempt in range(max_retries):
        try:
            table = Simbad.query_objects(list(object_names))
            if table is not None and len(table) > 0:
                #map names back; SIMBAD returns rows in input order, with a
                #user_specified_id / typed_id / MAIN_ID column depending on version
                id_col = None
                for candidate in ("user_specified_id", "USER_SPECIFIED_ID",
                                  "typed_id", "TYPED_ID", "MAIN_ID", "main_id"):
                    if candidate in table.colnames:
                        id_col = candidate
                        break

                if id_col is None and len(table) == len(object_names):
                    #fallback: assume same order as the input list
                    for i, name in enumerate(object_names):
                        try:
                            coords[name] = _coord_from_simbad_row(table[i])
                        except Exception:
                            pass
                else:
                    for i, name in enumerate(object_names):
                        try:
                            row = table[i] if (id_col is None) else None
                            if id_col is not None:
                                mask = [str(v).strip() == name for v in table[id_col]]
                                if any(mask):
                                    row = table[mask][0]
                            if row is not None:
                                coords[name] = _coord_from_simbad_row(row)
                        except Exception:
                            pass
            break  #batched call succeeded (even if some names didn't resolve)
        except Exception as e:
            if _is_simbad_transient_error(e) and attempt < max_retries - 1:
                print(f"SIMBAD batched query failed (transient: {e}); clearing cache and retrying...")
                _try_clear_simbad_cache()
                time.sleep(retry_wait_s)
                continue
            print(f"SIMBAD batched query failed ({e}); falling back to per-name queries.")
            break

    #for anything still unresolved, fall back to per-name queries with retries
    for name in object_names:
        if name in coords:
            continue
        for attempt in range(max_retries):
            try:
                result = Simbad.query_object(name)
                if result is None:
                    print(f"Could not resolve: {name}")
                    break
                coords[name] = _coord_from_simbad_row(result[0])
                break
            except Exception as e:
                if _is_simbad_transient_error(e) and attempt < max_retries - 1:
                    print(f"Transient SIMBAD error resolving {name} (attempt {attempt+1}/{max_retries}): {e}. "
                          f"Clearing cache and retrying in {retry_wait_s}s...")
                    _try_clear_simbad_cache()
                    time.sleep(retry_wait_s)
                    continue
                print(f"Error resolving {name}: {e}")
                break

    #remember whatever we learned, so a re-run costs nothing
    _COORD_CACHE.update(coords)

    return coords

def resolve_object_coords(object_dict):
    '''
    Function that gets RA,DEC co-ordinates of objects from object dictionary
    '''

    coords_dict = {}

    for ki in object_dict.keys():
        if ki != "planet" and len(object_dict[ki]) > 0:
            coords_dict[ki] = resolve_objects(object_dict[ki])
            
    return coords_dict


def build_time_grid_local(date, start_time, end_time, time_resolution_min=5, verbose=False):
    """
    Build an astropy Time array from local (Pacific) times.
    """

    start_dt = pacific.localize(datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M"))
    end_dt = pacific.localize(datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M"))

    if verbose:
        print("START:", start_dt)
        print("END:", end_dt)
    
    # Handle midnight crossing
    if end_dt <= start_dt:
        end_dt += pd.Timedelta(days=1)

    times_local = []
    current = start_dt

    while current <= end_dt:
        times_local.append(current)
        current += pd.Timedelta(minutes=time_resolution_min)

    # Convert to Astropy Time in UTC
    times_utc = Time(times_local)

    return times_utc


def altitude_curve(coord, times, location):
    """
    Compute altitude array for a SkyCoord over given times.
    """
    altaz = coord.transform_to(AltAz(obstime=times, location=location))
    return altaz.alt.deg


def altitude_curve_planet(planet_name, times, location):
    '''
    planet_name is a string like "jupiter"
    '''
    # Get Jupiter coordinates
    jupiter_coord = get_body(planet_name, times, location)

    # Compute altitudes
    altaz = jupiter_coord.transform_to(AltAz(obstime=times, location=location))
    alts_deg = altaz.alt.deg
    
    return alts_deg




def observable_targets(
    object_names,
    object_type,
    date,
    start_time,
    end_time,
    min_altitude=30.0,
    max_altitude=None,
    time_resolution_min=30,
    verbose=False):
    """
    Function that returns the table of objects that are observable in this time frame and their altitude trajectories
    
    Parameters
    ----------
    object_names : list of str
    object_type: str, "planet" or "not_planet"
    date : 'YYYY-MM-DD'
    start_time : 'HH:MM' (local time)
    end_time : 'HH:MM' (local time)
    min_altitude : float (degrees)
    max_altitude : float or None (degrees). Upper altitude limit, for mounts that
        track badly near the zenith (the eVscopes). An object only counts as
        observable while it sits inside [min_altitude, max_altitude], so a target
        that culminates overhead is still usable on its way up or down.
    time_resolution_min : int

    Returns
    -------
    pandas.DataFrame with observable targets. "max_altitude_deg" is the highest
    *usable* altitude, i.e. the peak of the altitude curve clipped to the band.
    """

    # Build time grid (local time assumed; Astropy handles conversion)
    times = build_time_grid_local(date, start_time, end_time, time_resolution_min,
                                  verbose=verbose)

    empty_df = pd.DataFrame(columns=[
            "name",
            "max_altitude_deg",
            "time_above_30min"
        ])

    if len(object_names) == 0:
        return empty_df, times, []
    
    if verbose:
        print(times[0].iso)
        print(times[0].to_datetime(timezone=pacific))
        
    tmp = []

    if object_type == "planet":
        if verbose:
            print("Object type is planet")
        coord_names = object_names
    else:
        # Resolve objects, this is a dictionary with the 
        obj_coords = resolve_objects(object_names)
        coord_names = obj_coords.keys()
    
    for name in coord_names:
        if object_type == "planet":
            altitudes = altitude_curve_planet(name, times, palo_alto_location)
        else:
            coord = obj_coords[name]
            altitudes = altitude_curve(coord, times, palo_alto_location)
    
        #only altitudes inside the telescope's usable band count
        in_band = altitude_in_band(altitudes, min_altitude, max_altitude)

        #if the object is ever usable in this window, add it to list!
        if np.any(in_band):
            #best altitude it actually reaches *while usable*
            max_alt = np.max(np.asarray(altitudes)[in_band])
            tmp.append((name, altitudes, max_alt, in_band))
        
    if len(tmp) == 0:
        return empty_df, times, []
    else:
        # Sort by max altitude
        tmp_sorted = sorted(tmp, key=lambda x: x[2], reverse=True)
        
        # Build DataFrame
        df = pd.DataFrame([{'name': t[0], 'max_altitude_deg': t[2],
                            'time_above_30min': max(np.sum(t[3]) - 1, 0) * time_resolution_min}
                        for t in tmp_sorted])

        # Extract all_alts in same order
        #all_alts is a list of time vs. altitude for the different objects under consideration
        all_alts = [t[1] for t in tmp_sorted]

    if verbose:
        print(f"all_alts shape = {np.shape(np.array(all_alts))}")

    return df, times, all_alts


def pick_best_objs(df_objs, alts_objs, num_objs):
    '''
    Function that picks the best objects based on how many we need
    '''
    # returnung the first 'num_objs' rows
    best_obj = df_objs.head(num_objs)['name'].tolist()
    best_obj_alts = alts_objs[:num_objs]
    # best_obj_notobstime = df_objs.head(num_objs)['time_above_30min'].tolist()

    return best_obj, best_obj_alts
    
    

def compute_object_score(object_alt, object_frac_notobs, alpha=100):
    '''
    This function computes the urgency score of an object based on how long it is observable and how high up it is.
    
    Higher score = higher priority
    
    Parameters:
    ----------
    object_alt: the altitude of object in deg under consideration
    object_frac_notobs: fraction of time [0,1] in the total interval left an object is not observable  (due to falling below 30 deg elevation)
    alpha: weight parameter
    '''
    
    if not (0 <= object_frac_notobs <= 1):
        raise ValueError("object_frac_notobs must be in [0,1]")
    
    return object_alt + alpha * object_frac_notobs
        



def select_optimal_ordering(time_local_datetimes, intervals, midpoints, chosen_objects, chosen_types, chosen_alts, min_altitude=30, max_altitude=None):
    '''
    In this function, we implement the optimal ordering scheme of the targets to observe
    
    Parameters:
    ------------
    time_local_datetimes: array of times 
    midpoints: list of midpoints in each observing interval 
    chosen_objects: list of object names under consideration
    chosen_alts: list of altitude trajectories as a function of time for each object under consideration
    '''
    
    if len(chosen_objects) != len(chosen_alts):
        raise ValueError("Object name and object altitude arrays do not have same number of objects")

    # Keep track of remaining objects, as we will not be repeating objects 
    remaining_indices = list(range(len(chosen_objects)))

    #Assign best object per interval (no repeats)
    schedule = []

    #Convert to datetime64
    time_np = time_local_datetimes.astype('datetime64[s]')
    
    if len(time_np) != len(chosen_alts[0]):
        raise ValueError("The time and altitude trajectory array do not have the same length!")


    #looping over each time interval (specifically the list of interval midpoints)
    for mp in midpoints:    
        # Convert to numpy datetime64
        mp_np = np.datetime64(mp)

        # Find closest index in times array
        idx_time = np.argmin(np.abs(time_np - mp_np))
        
        #WE NEED TO ONLY LOOK AT OBJECTS THAT ARE RIGTH NOW IN THIS INTERVAL ABOVE 30
        
        #there might be objects chosen that rise above 30 later and so do not want to be taken into consideration now

        # Look only at the object altitude at interval midpoint in remaining objects
        alts_at_mid = [chosen_alts[i][idx_time] for i in remaining_indices]
        
        #for these objects compute the notobstime for future, this will be updated at each interval
        frac_notobs_objs = []
        for i in remaining_indices:
            #get the future altitude trajectory
            alts_i = chosen_alts[i][idx_time:]
            time_np_i = time_np[idx_time:]
            #compute in the future how long it will be observable!
            tot_time_left = time_np[-1] - time_np_i[0]
            
            dt = np.diff(time_np)[0]  # timestep as timedelta64
            n_obs_left = np.sum(altitude_in_band(alts_i, min_altitude, max_altitude))
            tot_time_obs_left = max(n_obs_left - 1, 0) * dt
            
            if tot_time_left < 0 or tot_time_obs_left < 0:
                raise ValueError(f"tot_time is negative: {tot_time_obs_left}, {tot_time_left}")
                
            if tot_time_obs_left > tot_time_left:
                raise ValueError(f"tot_time_obs_left Cannot be larger than tot_time_left: {tot_time_obs_left}, {tot_time_left}")
                
            frac_notobs = 1 - (tot_time_obs_left/tot_time_left)
            frac_notobs_objs.append(frac_notobs)
            
        #compute the object scores for the objects left!!
        final_object_scores = []
        final_remain_idx = []
        for idx, remain_idx in enumerate(remaining_indices):
            
            if altitude_in_band(alts_at_mid[idx], min_altitude, max_altitude):
    
                score_i = compute_object_score(alts_at_mid[idx], frac_notobs_objs[idx])
        
                final_object_scores.append(score_i)
                final_remain_idx.append( remain_idx )


        # Pick the object with max score 
        best_local_idx = np.argmax(final_object_scores)
        chosen_idx = final_remain_idx[best_local_idx]

        #what is the elevation at which this object is being observed
        alts_at_mid =  np.array(alts_at_mid)
        obs_elevation = alts_at_mid[altitude_in_band(alts_at_mid, min_altitude, max_altitude)][best_local_idx]
        #is this object rising?

        if chosen_alts[chosen_idx][idx_time+1] > chosen_alts[chosen_idx][idx_time]:
            rising_flag = "rising"
        else:
            rising_flag = "falling"

        # Add to schedule
        interval_start = intervals[len(schedule)][0]
        interval_end   = intervals[len(schedule)][1]

        schedule.append({
            'object': chosen_objects[chosen_idx],
            'type': chosen_types[chosen_idx],
            'start': interval_start,
            'end': interval_end,
            'elev': int(obs_elevation),
            "path": rising_flag, 
        })

        # Remove this object from remaining
        remaining_indices.remove(chosen_idx)

    print("Unscheduled objects:", [chosen_objects[i] for i in remaining_indices])
        
    #Convert to DataFrame
    df_schedule = pd.DataFrame(schedule)

    return df_schedule



def create_observability_link(object_name, date, month, YYYY):
    '''
    Function to create observability links
    '''

    link_template = f"https://in-the-sky.org/data/object.php?id={object_name}&day={date}&month={month}&year={YYYY}"

    return link_template



def dt_to_timestr(dt):
    '''
    Function to convert time into a readable string
    '''
    return dt.strftime("%I:%M").lstrip("0")



def _build_row_dict(name_i, obj_type, elev, trajectory, interval_str, date_splits):
    '''
    Build a single row of the formatted catalog as a dict matching the standard columns.
    Used for both main schedule rows and alternate target rows.
    '''
    row = {}

    #object name (common name if available, else catalog name)
    if name_i in common_name:
        row["Name"] = common_name[name_i]
    else:
        row["Name"] = name_i
    row["Catalog Name"] = name_i

    #object type (resolve cluster sub-type if needed)
    if obj_type == "cluster":
        row["Object Type"] = cluster_type_mapping[name_i]
    else:
        row["Object Type"] = obj_type

    row["Elevation"] = elev
    row["Trajectory"] = trajectory
    row["Interval"] = interval_str

    row["Visibility Link"] = create_observability_link(name_i, date_splits[2], date_splits[1], date_splits[0])

    #outreach link by resolved object type
    if row["Object Type"] == "Open Cluster" or row["Object Type"] == "Globular Cluster":
        row["Outreach Info"] = outreach_link[row["Object Type"]]
    elif row["Object Type"] == "galaxy":
        row["Outreach Info"] = outreach_link["galaxy"]
    elif row["Object Type"] == "planet":
        row["Outreach Info"] = outreach_link["planet"]
    elif row["Object Type"] == "nebula":
        row["Outreach Info"] = outreach_link["nebula"]
    else:
        row["Outreach Info"] = ""

    return row


def _append_alternates(new_dict, df_alternates, date_splits, columns):
    '''
    Append an 'Alternate Targets' separator row plus one row per alternate target
    to the in-progress new_dict mapping (column -> list of values).
    '''
    if df_alternates is None or len(df_alternates) == 0:
        return

    #separator row: Name = "Alternate Targets", all other columns empty
    for ci in columns:
        if ci == "Name":
            new_dict[ci].append("Alternate Targets")
        else:
            new_dict[ci].append("")

    #one row per alternate
    for i, name_i in enumerate(df_alternates["object"].tolist()):
        path_i = df_alternates["path"].iloc[i]
        interval_str = "earlier in the night" if path_i == "falling" else "later at night"
        row = _build_row_dict(
            name_i,
            df_alternates["type"].iloc[i],
            df_alternates["elev"].iloc[i],
            path_i,
            interval_str,
            date_splits,
        )
        for ci in columns:
            new_dict[ci].append(row[ci])


def build_catalog_frames(df, date, split_table=1, df_alternates=None):
    '''
    Turn a schedule into the printable catalog table(s).

    Returns a list of DataFrames: one normally, or two when split_table=2 (the
    schedule dealt out alternately, so two telescopes of the same kind get
    different sheets). Each gets the same "Alternate Targets" block appended.

    format_table() writes these to output/; the web front end serves them as
    CSV downloads instead.
    '''

    date_splits = date.split("-")

    #the columns in the formatted catalog we want!
    columns = ["Name", "Object Type", "Elevation", "Trajectory", "Catalog Name", "Outreach Info", "Interval", "Visibility Link"]

    new_dict = {ci: [] for ci in columns}

    #build rows for the main schedule
    for i, name_i in enumerate(df["object"].tolist()):
        if name_i is None:
            #a slot nothing could fill; nothing to print for it
            continue
        interval_str = dt_to_timestr(df["start"][i]) + "-" + dt_to_timestr(df["end"][i])
        row = _build_row_dict(
            name_i,
            df["type"][i],
            df["elev"][i],
            df["path"][i],
            interval_str,
            date_splits,
        )
        for ci in columns:
            new_dict[ci].append(row[ci])

    #track how many rows belong to the main schedule (used for split_table=2)
    n_main = len(new_dict["Name"])

    #convert the dict to a dataframe(s)
    if split_table == 1:
        _append_alternates(new_dict, df_alternates, date_splits, columns)
        return [pd.DataFrame(new_dict)]

    if split_table == 2:
        #split only the main rows in an alternating way; both halves get the same alternates block
        df_main = pd.DataFrame({ci: new_dict[ci][:n_main] for ci in columns})

        df_1 = df_main.iloc[::2].copy() #even-indexed
        df_2 = df_main.iloc[1::2].copy() #odd-indexed

        if df_alternates is not None and len(df_alternates) > 0:
            alt_dict = {ci: [] for ci in columns}
            _append_alternates(alt_dict, df_alternates, date_splits, columns)
            df_alt_block = pd.DataFrame(alt_dict)

            df_1 = pd.concat([df_1, df_alt_block], ignore_index=True)
            df_2 = pd.concat([df_2, df_alt_block], ignore_index=True)

        return [df_1, df_2]

    raise ValueError(f"split_table must be 1 or 2, got {split_table}")


def format_table(df, date, telescope_type=None, split_table=1, df_alternates=None,
                 output_dir="output"):
    '''
    In this function, we format the table so we can save it as a csv file
    '''

    frames = build_catalog_frames(df, date, split_table=split_table,
                                  df_alternates=df_alternates)

    if len(frames) == 1:
        paths = [f"{output_dir}/catalog_{telescope_type}.csv"]
    else:
        paths = [f"{output_dir}/catalog_{telescope_type}_{i + 1}.csv"
                 for i in range(len(frames))]

    os.makedirs(output_dir, exist_ok=True)
    for frame, path in zip(frames, paths):
        frame.to_csv(path, index=False)

    return paths

 
def main_scheduler(date, start_time, end_time, num_cluster=0, num_nebula=0, num_galaxy=0, num_planet=0, num_point=0,
                    telescope_objs_dict=None, min_altitude=30, max_altitude=None,
                    split_table=1, verbose=True):
    '''
    Main function used to schedule targets for a given telescope and time information

    One telescope at a time. To couple the categories that several telescopes show
    at once -- the domes matching each other, the portables differing -- use
    schedule_group() or schedule_night() instead.

    Example:
    #date format is YYYY-MM-DD
    date = "2026-01-13"

    #local start time
    start_time = "18:30"
    #local end time
    end_time = "20:00"

    #need to know how many objects of each type do we need?
    num_cluster = 1
    num_nebula = 1
    num_planet = 1
    '''

    #time resolution for evaluating altitude
    time_resolution_min = 5

    quotas = {"cluster": num_cluster, "nebula": num_nebula, "galaxy": num_galaxy,
              "planet": num_planet, "point": num_point}
    tot_objects = sum(quotas.values())
    if tot_objects == 0:
        raise ValueError("Ask for at least one object")

    label = telescope_objs_dict["telescope_type"]
    telescope = {
        "label": label,
        "display": label,
        "targets": telescope_objs_dict,
        "max_altitude": max_altitude,
        "quotas": quotas,
    }

    results = schedule_group(
        date, start_time, end_time, [telescope], tot_objects,
        coupling="none", min_altitude=min_altitude,
        time_resolution_min=time_resolution_min, verbose=verbose)[label]

    df_schedule = results["schedule"]
    df_alternates = results["alternates"]

    #write the csv(s), honouring split_table
    format_table(df_schedule, date, label, split_table=split_table,
                 df_alternates=df_alternates)

    if verbose:
        print(df_schedule)
        if len(df_alternates) > 0:
            print(f"Alternates: {df_alternates['object'].tolist()}")

    ##return stuff

    times = build_time_grid_local(date, start_time, end_time, time_resolution_min)
    time_local_datetimes = np.array(
        [t.replace(tzinfo=None) for t in times.to_datetime(timezone=pacific)])

    scheduled = df_schedule["object"].tolist()
    types = df_schedule["type"].tolist()

    return_dict = {"time_local_datetimes": time_local_datetimes,
                    "df_schedule": df_schedule,
                    "df_alternates": df_alternates}

    for class_i in OBJECT_CLASSES:
        return_dict["best_" + class_i] = [o for o, ty in zip(scheduled, types)
                                          if ty == class_i]
        return_dict["df_" + class_i] = results["observable"][class_i]
        return_dict["alts_" + class_i] = [c["alts"] for c in results["candidates"]
                                          if c["cls"] == class_i]

    if verbose:
        for class_i in OBJECT_CLASSES:
            if quotas[class_i] > 0:
                print(f"Best {class_i}: {return_dict['best_' + class_i]}")

    return return_dict

#### GROUP SCHEDULING
#
# The three telescopes-at-once rules all need telescopes scheduled *together* on
# one shared clock, which is what schedule_group does:
#
#   coupling="diverse" the telescopes show DIFFERENT categories in each interval.
#                      For the portable line, which visitors walk end to end in
#                      one go, so five minutes gets them five kinds of object.
#                      Also the better setting for the two domes -- see below.
#
#   coupling="match"   the telescopes in the group show the SAME category in each
#                      interval, synchronising them onto one varied sequence.
#
#                      This only helps when the telescopes can actually show the
#                      same things. Ours cannot: the 24-inch is an eyepiece and
#                      the 0.7 m takes long exposures, so their lists barely
#                      overlap (the 24-inch owns no galaxies at all). Matching
#                      then confines both domes to the thin shared repertoire,
#                      which measurably backfires -- over a year of test nights a
#                      visitor who saw one dome and later the other hit the same
#                      category 26% of the time under "match" but only 17% under
#                      "diverse", while the 0.7 m's galaxy time fell from 49% to
#                      12% and each dome lost a target per night. Kept because it
#                      is the right choice for two similar telescopes.
#
#   coupling="none"    telescopes are scheduled independently (old behaviour).


#How strongly the category rule pulls against simply pointing at whatever is
#highest in the sky. Object scores run ~30-190 (altitude plus an urgency bonus).
#Swept over a year of dates, raising this to ~150 takes the category rules from
#holding ~65% of intervals to ~90% while *raising* the mean altitude observed
#slightly, so there is no real trade-off here -- anything lower just gives up
#compliance for nothing. Past ~150 the remaining misses are genuine: a telescope
#that owns no galaxies cannot match a galaxy, however much we pay it.
COUPLING_WEIGHT = 150.0

#Showing the same object twice in a group. Two telescopes are never pointed at
#the same object *simultaneously*, but reusing one later in the night depends on
#who is watching: on the portable line, where visitors walk past every telescope,
#a repeat wastes a slot and is worth avoiding strongly. Between the two domes,
#where nobody reaches both, a repeat costs a visitor nothing -- so the penalty
#stays below COUPLING_WEIGHT and never talks a dome out of matching its partner.
GROUP_REPEAT_PENALTY = {"diverse": 150.0, "none": 150.0, "match": 40.0}

#One telescope showing the same category it just showed. This is what makes a
#single telescope's own night walk through cluster, nebula, galaxy rather than
#sitting on one kind of object, and for the domes it is the *main* thing
#delivering variety to a visitor (see the note on "match" below). Swept over a
#year of dates: 75 maxes out each telescope's own spread; past ~150 it starts
#hurting, because forcing a change of category pushes telescopes onto whatever
#is left, which collides with the other dome more often, not less.
SEQUENCE_VARIETY_PENALTY = 75.0

#Leaving a telescope with nothing this interval. Dwarfs every other term, so a
#combination that keeps everyone busy always wins; it only bites when there are
#genuinely fewer distinct objects in reach than telescopes pointing at them.
UNFILLED_PENALTY = 1000.0


def _telescope_candidates(telescope, date, start_time, end_time, min_altitude,
                          time_resolution_min, verbose=False):
    '''
    Work out everything one telescope could look at tonight.

    Returns (candidates, times, df_by_class) where candidates is a list of
        {"name", "cls", "alts", "peak"}
    for every target that spends some time inside this telescope's altitude band.
    '''
    max_altitude = telescope.get("max_altitude")
    targets = telescope["targets"]

    candidates = []
    df_by_class = {}
    times = None

    for cls in OBJECT_CLASSES:
        names = targets.get(cls, [])
        object_type = "planet" if cls == "planet" else "not_planet"

        if len(names) == 0:
            df_by_class[cls] = pd.DataFrame(
                columns=["name", "max_altitude_deg", "time_above_30min"])
            if times is None:
                times = build_time_grid_local(date, start_time, end_time,
                                              time_resolution_min, verbose=verbose)
            continue

        df_cls, times, alts_cls = observable_targets(
            object_names=names,
            object_type=object_type,
            date=date,
            start_time=start_time,
            end_time=end_time,
            min_altitude=min_altitude,
            max_altitude=max_altitude,
            time_resolution_min=time_resolution_min,
            verbose=verbose,
        )
        df_by_class[cls] = df_cls

        for i, name in enumerate(df_cls["name"].tolist()):
            candidates.append({
                "name": name,
                "cls": cls,
                "alts": np.asarray(alts_cls[i], dtype=float),
                "peak": float(df_cls["max_altitude_deg"].iloc[i]),
            })

    return candidates, times, df_by_class


def _candidate_score(candidate, idx_time, time_np, min_altitude, max_altitude):
    '''
    Urgency score for one candidate at one instant: high in the sky is good, and
    running out of night is better still (compute_object_score does the mixing).
    '''
    alts_future = candidate["alts"][idx_time:]

    total_left = time_np[-1] - time_np[idx_time]
    if total_left <= np.timedelta64(0, 's'):
        #last interval: nothing is more urgent than anything else
        frac_notobs = 0.0
    else:
        dt = np.diff(time_np)[0]
        n_usable = np.sum(altitude_in_band(alts_future, min_altitude, max_altitude))
        obs_left = max(n_usable - 1, 0) * dt
        frac_notobs = float(1 - (obs_left / total_left))
        frac_notobs = min(max(frac_notobs, 0.0), 1.0)

    return compute_object_score(float(candidate["alts"][idx_time]), frac_notobs)


def _coupling_bonus(classes, coupling, last_classes=None):
    '''
    Reward for a set of per-telescope category choices in one interval.

    "match" pays for every telescope beyond the first that agrees with the others;
    "diverse" pays for every distinct category on show. Either way a telescope is
    docked a little for repeating the category it showed last interval.
    '''
    if coupling == "match":
        bonus = COUPLING_WEIGHT * (len(classes) - len(set(classes)))
    elif coupling == "diverse":
        bonus = COUPLING_WEIGHT * len(set(classes))
    else:
        bonus = 0.0

    if last_classes is not None:
        for cls, last in zip(classes, last_classes):
            if last is not None and cls == last:
                bonus -= SEQUENCE_VARIETY_PENALTY

    return bonus


def _assign_profile(profile, ranked, already_shown, repeat_penalty):
    '''
    Try to hand out one object per telescope, following `profile` (the category
    each telescope is meant to show this interval).

    profile : tuple of class names, one per telescope
    ranked  : ranked[t][cls] = list of (score, name) best first
    already_shown : object names another telescope in the group used earlier
    repeat_penalty : cost of reusing one of those (see GROUP_REPEAT_PENALTY)

    Two telescopes are never pointed at the same object in the same interval, so
    when they share a category they take the first and second best object in it.
    If there are fewer distinct objects in reach than telescopes wanting them,
    the leftovers get None rather than a duplicate, at UNFILLED_PENALTY each --
    which is what makes the search prefer categories that keep everyone busy.

    Returns (total_score, picks), where picks may contain None.
    '''
    claimed = set()
    picks = [None] * len(profile)
    total = 0.0

    #telescopes with the strongest claim choose first, so the best object in a
    #shared category goes to whoever gains most from it
    order = sorted(
        range(len(profile)),
        key=lambda t: ranked[t][profile[t]][0][0] if ranked[t].get(profile[t]) else -np.inf,
        reverse=True,
    )

    for t in order:
        options = ranked[t].get(profile[t]) or []
        best = None
        for score, name in options:
            if name in claimed:
                continue
            if name in already_shown:
                score = score - repeat_penalty
            if best is None or score > best[0]:
                best = (score, name)
                #options are sorted, so the first unclaimed one is already the
                #best unless a repeat penalty applies; keep looking in that case
                if name not in already_shown:
                    break

        if best is None:
            #every object of this category is already on another telescope
            total -= UNFILLED_PENALTY
            continue

        claimed.add(best[1])
        picks[t] = best[1]
        total += best[0]

    return total, picks


def select_group_ordering(times, intervals, midpoints, telescopes, candidates_by_tel,
                          coupling="none", min_altitude=30.0, verbose=False):
    '''
    Fill every interval on every telescope in the group at once.

    For each interval we score each telescope's still-unused, currently-pointable
    targets, then pick the combination of categories that scores best once the
    coupling bonus is added. Enumerating category combinations (at most 5 per
    telescope) is cheap at these group sizes and, unlike choosing telescope by
    telescope, it will not paint the group into a corner -- e.g. letting the 0.7 m
    take a galaxy in a "match" interval when the 24-inch has no galaxies to match
    it with.

    Returns {label: DataFrame} with one row per interval.
    '''
    time_np = np.asarray(times).astype('datetime64[s]')

    used = {t["label"]: set() for t in telescopes}       #per telescope, no repeats
    shown_in_group = set()                                #across the group tonight
    schedules = {t["label"]: [] for t in telescopes}
    last_classes = [None] * len(telescopes)               #what each showed last interval
    repeat_penalty = GROUP_REPEAT_PENALTY.get(coupling, 150.0)
    notes = []                                            #anything the operator should know

    #how many of each category each telescope has been asked for, if anything
    quota_left = {}
    for t in telescopes:
        quotas = t.get("quotas")
        quota_left[t["label"]] = dict(quotas) if quotas else None

    for k, mp in enumerate(midpoints):
        idx_time = int(np.argmin(np.abs(time_np - np.datetime64(mp))))

        #what can each telescope point at right now, ranked within each category
        def pointable(t, allow_used):
            max_altitude = t.get("max_altitude")
            quotas = quota_left[t["label"]]
            by_class = {}
            for cand in candidates_by_tel[t["label"]]:
                if not allow_used and cand["name"] in used[t["label"]]:
                    continue
                #a telescope asked for e.g. exactly one cluster stops offering
                #clusters once it has had one
                if quotas is not None and quotas.get(cand["cls"], 0) <= 0:
                    continue
                if not altitude_in_band(cand["alts"][idx_time], min_altitude, max_altitude):
                    continue
                score = _candidate_score(cand, idx_time, time_np, min_altitude, max_altitude)
                by_class.setdefault(cand["cls"], []).append((score, cand["name"]))
            for cls in by_class:
                by_class[cls].sort(reverse=True)
            return by_class

        #A telescope can genuinely run dry mid-window -- everything it owns has
        #either been shown already or is out of its altitude band right now. That
        #is no reason to throw away the whole event's schedule, so fall back to
        #showing one of its earlier targets again, and only leave the slot empty
        #if even that is impossible. Both cases are reported in `notes`.
        ranked = []
        reusing = []
        for t in telescopes:
            by_class = pointable(t, allow_used=False)
            repeat = False
            if len(by_class) == 0:
                by_class = pointable(t, allow_used=True)
                repeat = len(by_class) > 0
                if repeat:
                    notes.append(
                        f"{t['label']} had nothing new above the horizon at "
                        f"{dt_to_timestr(mp)}, so it shows an earlier target again."
                    )
                else:
                    notes.append(
                        f"{t['label']} has nothing it can point at around "
                        f"{dt_to_timestr(mp)} -- that slot is left open."
                    )
            ranked.append(by_class)
            reusing.append(repeat)

        #telescopes with nothing at all sit this interval out
        active = [i for i, r in enumerate(ranked) if len(r) > 0]
        idle = [i for i, r in enumerate(ranked) if len(r) == 0]

        #best combination of categories across the group. The number of
        #combinations is (classes ** telescopes), so bound each one by its best
        #possible score before doing the real assignment and skip the hopeless ones
        best = (None, None, None)
        sub_ranked = [ranked[i] for i in active]
        sub_last = [last_classes[i] for i in active]
        ceiling = [{cls: opts[0][0] for cls, opts in r.items()} for r in sub_ranked]

        for profile in itertools.product(*[sorted(r.keys()) for r in sub_ranked]):
            bonus = _coupling_bonus(profile, coupling, sub_last)
            bound = sum(ceiling[t][cls] for t, cls in enumerate(profile)) + bonus
            if best[0] is not None and bound <= best[0]:
                continue

            total, picks = _assign_profile(profile, sub_ranked, shown_in_group,
                                           repeat_penalty)
            total += bonus
            if best[0] is None or total > best[0]:
                best = (total, profile, picks)

        interval_start, interval_end = intervals[k]
        _, profile, picks = best

        chosen = {}
        for slot, i in enumerate(active):
            if picks[slot] is None:
                #fewer distinct objects in reach than telescopes; better an open
                #slot the operator can fill than two telescopes on one object
                notes.append(
                    f"{telescopes[i]['label']} shares its only remaining options with "
                    f"another telescope at {dt_to_timestr(mp)}, so that slot is left open."
                )
                last_classes[i] = None
            else:
                chosen[i] = (profile[slot], picks[slot])
                last_classes[i] = profile[slot]

        for i in idle:
            last_classes[i] = None

        for i, t in enumerate(telescopes):
            if i in chosen:
                cls, name = chosen[i]
                cand = next(c for c in candidates_by_tel[t["label"]] if c["name"] == name)
                alts = cand["alts"]

                #is it on the way up or on the way down?
                nxt = min(idx_time + 1, len(alts) - 1)
                rising_flag = "rising" if alts[nxt] > alts[idx_time] else "falling"

                schedules[t["label"]].append({
                    'object': name,
                    'type': cls,
                    'start': interval_start,
                    'end': interval_end,
                    'elev': int(alts[idx_time]),
                    'path': rising_flag,
                    'repeat': name in used[t["label"]],
                })

                used[t["label"]].add(name)
                shown_in_group.add(name)
                if quota_left[t["label"]] is not None:
                    quota_left[t["label"]][cls] -= 1
            else:
                #nothing pointable: keep the row so every telescope in the group
                #stays on the same interval grid, but leave it blank
                schedules[t["label"]].append({
                    'object': None,
                    'type': None,
                    'start': interval_start,
                    'end': interval_end,
                    'elev': None,
                    'path': None,
                    'repeat': False,
                })

        if verbose:
            summary = ", ".join(
                f"{t['label']}={chosen[i][1]} ({chosen[i][0]})" if i in chosen
                else f"{t['label']}=(open)"
                for i, t in enumerate(telescopes))
            print(f"  {dt_to_timestr(interval_start)}-{dt_to_timestr(interval_end)}: {summary}")

    return {label: pd.DataFrame(rows) for label, rows in schedules.items()}, notes


def build_intervals(date, start_time, end_time, num_slots):
    '''
    Chop the observing window into num_slots equal intervals, and give back their
    midpoints too (which is where we evaluate altitudes).
    '''
    if num_slots < 1:
        raise ValueError(f"Need at least one target per telescope, got {num_slots}")

    start_dt = pd.to_datetime(f"{date} {start_time}")
    end_dt = pd.to_datetime(f"{date} {end_time}")
    if end_dt <= start_dt:
        #window runs past midnight
        end_dt += pd.Timedelta(days=1)

    total_minutes = int((end_dt - start_dt).total_seconds() / 60)
    minutes_per_target = total_minutes // num_slots
    if minutes_per_target < 1:
        raise ValueError(
            f"{num_slots} targets in {total_minutes} minutes leaves under a minute each"
        )

    intervals = []
    current_start = start_dt
    for _ in range(num_slots):
        current_end = current_start + pd.Timedelta(minutes=minutes_per_target)
        intervals.append((current_start, current_end))
        current_start = current_end

    midpoints = [s + (e - s) / 2 for s, e in intervals]

    return intervals, midpoints, minutes_per_target


def _build_alternates(candidates, chosen_names, num_alternates=3):
    '''
    The best few targets we did not schedule, as a fallback for the operator.
    '''
    pool = [c for c in candidates if c["name"] not in chosen_names]
    pool.sort(key=lambda c: c["peak"], reverse=True)

    rows = []
    for cand in pool[:num_alternates]:
        alts = cand["alts"]
        rows.append({
            'object': cand["name"],
            'type': cand["cls"],
            'elev': int(round(cand["peak"])),
            'path': "rising" if alts[-1] > alts[0] else "falling",
        })

    return pd.DataFrame(rows, columns=['object', 'type', 'elev', 'path'])


def matchable_capacity(telescopes, candidates_by_tel):
    '''
    How many intervals a "match" group can keep agreeing for.

    Each matched interval spends one object of the agreed category at *every*
    telescope, so a category is only good for as many intervals as its thinnest
    list allows: with 4 clusters at one dome and 3 at the other, clusters carry 3
    intervals. Summing that over the categories both can serve gives the ceiling.

    This is why the 24-inch's list matters so much -- it owns no galaxies, so
    galaxies contribute nothing to the domes' ceiling no matter how many the
    0.7 m has.
    '''
    per_telescope = {}
    for t in telescopes:
        counts = {}
        for cand in candidates_by_tel[t["label"]]:
            counts[cand["cls"]] = counts.get(cand["cls"], 0) + 1
        per_telescope[t["label"]] = counts

    classes = set()
    for counts in per_telescope.values():
        classes.update(counts)

    return sum(min(per_telescope[t["label"]].get(cls, 0) for t in telescopes)
               for cls in classes)


def recommend_slots(date, start_time, end_time, telescopes, min_altitude=30.0,
                    time_resolution_min=5, candidates_by_tel=None, coupling="none"):
    '''
    Suggest how many targets each telescope in a group should work through.

    Three things bound it. The clock: an interval has to be long enough for the
    slowest telescope in the group to re-point and let a queue of people look
    (minutes_per_target in target_lists.py). The sky: you cannot schedule six
    objects at a telescope that can only reach four tonight. And, for a matched
    group, the lists themselves -- asking the domes for more targets than they can
    agree on just buys repeated categories, which is the opposite of the point, so
    the count is trimmed to what they can actually match on.

    Returns {"num_slots", "window_minutes", "pace", "pace_limit", "available",
             "limited_by", "reason"} -- the numbers as well as the answer, so the
    page can explain itself and the operator can overrule it.
    '''
    start_dt = pd.to_datetime(f"{date} {start_time}")
    end_dt = pd.to_datetime(f"{date} {end_time}")
    if end_dt <= start_dt:
        end_dt += pd.Timedelta(days=1)
    window = int((end_dt - start_dt).total_seconds() / 60)

    #the group shares one interval grid, so the slowest telescope sets the pace
    pace = max(t.get("minutes_per_target") or 20 for t in telescopes)
    pace_limit = max(1, window // pace)

    #how many objects each telescope can actually reach tonight
    if candidates_by_tel is None:
        candidates_by_tel = {}
        for t in telescopes:
            cands, _, _ = _telescope_candidates(
                t, date, start_time, end_time, min_altitude, time_resolution_min)
            candidates_by_tel[t["label"]] = cands

    available = min(len(candidates_by_tel[t["label"]]) for t in telescopes)

    #never trim a matched group below this: two targets is the least that still
    #shows a visitor any variety at all
    MIN_MATCHED_SLOTS = 2

    match_limit = None
    if coupling == "match" and len(telescopes) > 1:
        match_limit = max(MIN_MATCHED_SLOTS,
                          matchable_capacity(telescopes, candidates_by_tel))

    limits = [pace_limit, available] + ([match_limit] if match_limit else [])
    num_slots = max(1, min(limits))

    if match_limit is not None and match_limit == num_slots < min(pace_limit, available):
        limited_by = "matching"
        reason = (f"the telescopes can only agree on {match_limit} categories-worth "
                  f"of objects tonight; more targets than that would just repeat "
                  f"categories")
    elif available <= min(pace_limit, match_limit or pace_limit):
        thin = min(telescopes, key=lambda t: len(candidates_by_tel[t["label"]]))
        limited_by = "targets"
        reason = (f"{thin['label']} can only reach {available} object(s) tonight, "
                  f"so that caps the group")
    else:
        limited_by = "time"
        reason = (f"{window} min at about {pace} min per object "
                  f"(the slowest telescope in the group)")

    return {
        "num_slots": int(num_slots),
        "window_minutes": window,
        "pace": int(pace),
        "pace_limit": int(pace_limit),
        "available": int(available),
        "match_limit": int(match_limit) if match_limit is not None else None,
        "limited_by": limited_by,
        "reason": reason,
    }


def schedule_group(date, start_time, end_time, telescopes, num_slots=None,
                   coupling="none", min_altitude=30.0, time_resolution_min=5,
                   num_alternates=3, write_csv=False, output_dir="output",
                   verbose=True):
    '''
    Schedule a set of telescopes that share one observing window, coupling their
    object categories.

    Parameters
    ----------
    date : 'YYYY-MM-DD'
    start_time, end_time : 'HH:MM' local (Pacific)
    telescopes : list of instance dicts from target_lists.build_roster(), each
        {"label", "targets", "max_altitude", ...} and optionally
        "quotas" : {class: how many of that class this telescope should get}
    num_slots : how many targets each telescope works through tonight. One shared
        interval grid is what makes "same category at the same time" meaningful.
        Pass None to let recommend_slots() work it out from the window length, the
        telescopes' pace and what is actually up.
    coupling : "match" (domes), "diverse" (portables) or "none"
    min_altitude : floor in degrees, applied to every telescope
    write_csv : also write output_dir/catalog_<label>.csv

    Returns
    -------
    dict keyed by telescope label, each
        {"display", "schedule", "catalog", "csv", "alternates", "observable"}
    '''
    if coupling not in ("match", "diverse", "none"):
        raise ValueError(f"coupling must be 'match', 'diverse' or 'none', got {coupling!r}")
    if len(telescopes) == 0:
        return {}

    #what each telescope could look at tonight
    candidates_by_tel = {}
    observable_by_tel = {}
    times = None
    for t in telescopes:
        cands, times, df_by_class = _telescope_candidates(
            t, date, start_time, end_time, min_altitude, time_resolution_min)
        candidates_by_tel[t["label"]] = cands
        observable_by_tel[t["label"]] = df_by_class

        if verbose:
            by_cls = {}
            for c in cands:
                by_cls.setdefault(c["cls"], []).append(c["name"])
            print(f"  {t['label']}: " + ("; ".join(
                f"{cls} x{len(v)}" for cls, v in by_cls.items()) or "nothing observable"))

    recommendation = recommend_slots(
        date, start_time, end_time, telescopes, min_altitude=min_altitude,
        time_resolution_min=time_resolution_min, candidates_by_tel=candidates_by_tel,
        coupling=coupling)

    if num_slots is None:
        num_slots = recommendation["num_slots"]
        if verbose:
            print(f"  suggested {num_slots} targets each: {recommendation['reason']}")

    for t in telescopes:
        if len(candidates_by_tel[t["label"]]) < num_slots:
            raise ValueError(
                f"{t['label']} can only reach {len(candidates_by_tel[t['label']])} "
                f"target(s) in this window but needs {num_slots}. Widen the window, ask "
                f"for fewer targets, or add objects to its list."
            )

    for t in telescopes:
        quotas = t.get("quotas")
        if quotas and sum(quotas.values()) != num_slots:
            raise ValueError(
                f"{t['label']}: per-category counts add up to {sum(quotas.values())} "
                f"but the group has {num_slots} slots per telescope"
            )

    intervals, midpoints, minutes_per_target = build_intervals(
        date, start_time, end_time, num_slots)

    if verbose:
        labels = ", ".join(t["label"] for t in telescopes)
        print(f"== {labels} | coupling={coupling} | "
              f"{num_slots} targets x ~{minutes_per_target} min ==")

    time_local_datetimes = np.array(
        [ti.replace(tzinfo=None) for ti in times.to_datetime(timezone=pacific)])

    schedules, notes = select_group_ordering(
        time_local_datetimes, intervals, midpoints, telescopes, candidates_by_tel,
        coupling=coupling, min_altitude=min_altitude, verbose=verbose)

    if verbose:
        for note in notes:
            print(f"  note: {note}")

    results = {}
    for t in telescopes:
        label = t["label"]
        df_schedule = schedules[label]
        chosen = set(n for n in df_schedule["object"].tolist() if n is not None)

        df_alternates = _build_alternates(
            candidates_by_tel[label], chosen, num_alternates=num_alternates)

        catalog = build_catalog_frames(df_schedule, date, split_table=1,
                                       df_alternates=df_alternates)[0]

        if write_csv:
            os.makedirs(output_dir, exist_ok=True)
            catalog.to_csv(f"{output_dir}/catalog_{label}.csv", index=False)

        results[label] = {
            "display": t.get("display", label),
            #notes naming this telescope, plus the group-wide ones
            "notes": [n for n in notes if n.startswith(label)],
            "group_notes": list(notes),
            "schedule": df_schedule,
            "catalog": catalog,
            "csv": catalog.to_csv(index=False),
            "alternates": df_alternates,
            "observable": observable_by_tel[label],
            "candidates": candidates_by_tel[label],
            "num_slots": num_slots,
            "minutes_per_target": minutes_per_target,
            "recommendation": recommendation,
        }

    return results


def schedule_night(date, start_time, end_time, groups=None, roster=None,
                   num_slots=None, slots_by_group=None, quotas_by_telescope=None,
                   min_altitude=30.0, time_resolution_min=5, num_alternates=3,
                   write_csv=False, output_dir="output", verbose=True):
    '''
    Schedule a whole event: every group of telescopes, each with its own coupling.

    This is the entry point the web front end calls.

    Parameters
    ----------
    groups : list of {"name", "telescopes": [label, ...], "coupling"}.
        Defaults to target_lists.default_groups(roster) -- domes matched,
        portables diversified.
    roster : list of telescope instances from target_lists.build_roster().
    num_slots : targets per telescope, for any group not named in slots_by_group.
        None (the default) asks recommend_slots() to work it out per group.
    slots_by_group : {group name: targets per telescope}, for when the domes
        should linger on fewer objects than the portable line. A None value for a
        group means "recommend one for this group".
    quotas_by_telescope : {label: {class: count}} to pin down categories.

    Returns
    -------
    {"date", "start_time", "end_time", "groups": [...], "telescopes": {label: ...}}
    '''
    if roster is None:
        roster = build_roster()
    if groups is None:
        groups = default_groups(roster)

    by_label = {t["label"]: t for t in roster}
    unknown = [lab for g in groups for lab in g["telescopes"] if lab not in by_label]
    if unknown:
        raise ValueError(f"Not in the roster: {', '.join(unknown)}")

    all_results = {}
    group_summaries = []

    for group in groups:
        labels = group["telescopes"]
        if len(labels) == 0:
            continue

        slots = (slots_by_group or {}).get(group["name"], num_slots)

        telescopes = []
        for lab in labels:
            t = dict(by_label[lab])
            if quotas_by_telescope and lab in quotas_by_telescope:
                t["quotas"] = quotas_by_telescope[lab]
            telescopes.append(t)

        #a group of one has nothing to couple with
        coupling = group.get("coupling", "none")
        if len(telescopes) == 1:
            coupling = "none"

        results = schedule_group(
            date, start_time, end_time, telescopes, slots,
            coupling=coupling, min_altitude=min_altitude,
            time_resolution_min=time_resolution_min, num_alternates=num_alternates,
            write_csv=write_csv, output_dir=output_dir, verbose=verbose)

        all_results.update(results)
        first_result = next(iter(results.values()))
        group_notes = list(first_result["group_notes"])
        first = first_result
        group_summaries.append({
            "name": group["name"],
            "coupling": coupling,
            "telescopes": labels,
            "num_slots": first["num_slots"],
            "minutes_per_target": first["minutes_per_target"],
            "auto_slots": slots is None,
            "recommendation": first["recommendation"],
            "notes": group_notes,
        })

    return {
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "groups": group_summaries,
        "telescopes": all_results,
    }
