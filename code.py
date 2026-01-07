import numpy as np
import pandas as pd
from datetime import timedelta

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from astroquery.simbad import Simbad
from astropy.coordinates import EarthLocation, AltAz, get_body
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import pytz
from datetime import datetime

pacific = pytz.timezone("US/Pacific")

# Palo Alto, CA
palo_alto_location = EarthLocation(
    lat=37.4419 * u.deg,
    lon=-122.1430 * u.deg,
    height=50 * u.m # assuming some random small height
)

def resolve_objects(object_names):
    """
    For extra-galactic objects
    Resolve object names to SkyCoord using SIMBAD.
    Returns dict: name -> SkyCoord
    """
    coords = {}

    for name in object_names:
        try:
            result = Simbad.query_object(name)
            if result is None:
                print(f"Could not resolve: {name}")
                continue
                                
            ra = result["ra"][0]
            dec = result["dec"][0]
            coord = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame="icrs")
            coords[name] = coord

        except Exception as e:
            print(f"Error resolving {name}: {e}")

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


def build_time_grid_local(date, start_time, end_time, time_resolution_min=5):
    """
    Build an astropy Time array from local (Pacific) times.
    """

    start_dt = pacific.localize(datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M"))
    
    print("START:", start_dt)
    
    end_dt = pacific.localize(datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M"))
    
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
    time_resolution_min : int

    Returns
    -------
    pandas.DataFrame with observable targets
    """

    # Build time grid (local time assumed; Astropy handles conversion)
    times = build_time_grid_local(date, start_time, end_time, time_resolution_min)

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
    
        max_alt = np.max(altitudes)
        
        #if the object ever exceeds the min altitude of consideration, add it to list!
        if max_alt >= min_altitude:
            tmp.append((name, altitudes, max_alt))        
        
    if len(tmp) == 0:
        return empty_df, times, []
    else:
        # Sort by max altitude
        tmp_sorted = sorted(tmp, key=lambda x: x[2], reverse=True)
        
        # Build DataFrame
        df = pd.DataFrame([{'name': t[0], 'max_altitude_deg': t[2],
                            'time_above_30min': (np.sum(t[1] >= min_altitude) - 1) * time_resolution_min}
                        for t in tmp_sorted])

        # Extract all_alts in same order
        #all_alts is a list of time vs. altitude for the different objects under consideration
        all_alts = [t[1] for t in tmp_sorted]

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
        



def select_optimal_ordering(time_local_datetimes, intervals, midpoints, chosen_objects, chosen_types, chosen_alts, min_altitude=30):
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
            tot_time_obs_left = (np.sum(alts_i >= min_altitude) - 1) * dt
            
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
            
            if alts_at_mid[idx] > min_altitude:
    
                score_i = compute_object_score(alts_at_mid[idx], frac_notobs_objs[idx])
        
                final_object_scores.append(score_i)
                final_remain_idx.append( remain_idx )


        # Pick the object with max score 
        best_local_idx = np.argmax(final_object_scores)
        chosen_idx = final_remain_idx[best_local_idx]

        #what is the elevation at which this object is being observed
        alts_at_mid =  np.array(alts_at_mid)
        obs_elevation = alts_at_mid[alts_at_mid > min_altitude][best_local_idx]
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

        
    #Convert to DataFrame
    df_schedule = pd.DataFrame(schedule)
    print(df_schedule)
    
    return df_schedule



def create_observability_link(object_name, date, month, YYYY):
    '''
    Function to create observability links
    '''

    link_template = f"https://in-the-sky.org/data/object.php?id={object_name}&day={date}&month={month}&year={YYYY}"

    return link_template

 
def main_scheduler(date, start_time, end_time, num_cluster=0, num_nebula=0, num_galaxy=0, num_planet=0, num_point=0,
                    telescope_objs_dict=None,min_altitude=30):
    '''
    Main function used to schedule targets for a given telescope and time information

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

    # obj_coords = resolve_object_coords(telescope_objs_dict)

    tot_objects = num_cluster + num_nebula + num_planet + num_galaxy
    #the total number of objects will determine how many minutes per object

    # total observing window in minutes
    start_dt = pd.to_datetime(f"{date} {start_time}")
    end_dt   = pd.to_datetime(f"{date} {end_time}")
    total_minutes = int((end_dt - start_dt).total_seconds() / 60)

    # divide time equally among all targets
    minutes_per_target = total_minutes // tot_objects

    print(f"Approx {minutes_per_target} mins per target!")

    ##get the object observabilities
    ##loop through each object type

    print("=="*5)

    object_classes = ["cluster", "nebula", "galaxy", "planet", "point"]
    object_types = ["not_planet","not_planet","not_planet","planet", "not_planet"]
    object_nums = [num_cluster, num_nebula, num_galaxy, num_planet, num_point]

    all_dfs = {}
    all_alts = {}

    for idx,class_i in enumerate(object_classes):

        if len(telescope_objs_dict[class_i]) == 0:
            #if there are no objects of this class in target list

            print(f"There are no objects for class {class_i} for this telescope")

            times = build_time_grid_local(date, start_time, end_time, time_resolution_min)

            df_class_i = pd.DataFrame(columns=[
                "name",
                "max_altitude_deg",
                "time_above_30min"
            ])

            alts_class_i = []

        else:
            df_class_i, times, alts_class_i  = observable_targets(
                object_names=telescope_objs_dict[class_i],
                object_type=object_types[idx],
                date=date,
                start_time=start_time,
                end_time=end_time,
                min_altitude=min_altitude,
                time_resolution_min=time_resolution_min,
            )

        all_dfs[class_i] = df_class_i
        all_alts[class_i] = alts_class_i

        print(f"Total {len(df_class_i)} objects observable in class:{class_i} = {df_class_i['name'].tolist()}")

        if len(df_class_i) < object_nums[idx]:
            raise ValueError(f"You are requesting more objects ({object_nums[idx]}) in {class_i} class than are observable ({len(df_class_i)})!")

        print("--"*2)

    print("=="*5)
    #these the objects that have the highest elevation in the night
    best_cluster, best_cluster_alts = pick_best_objs(all_dfs["cluster"], all_alts["cluster"], num_cluster)
    best_nebula, best_nebula_alts = pick_best_objs(all_dfs["nebula"], all_alts["nebula"], num_nebula)
    best_galaxy, best_galaxy_alts = pick_best_objs(all_dfs["galaxy"], all_alts["galaxy"], num_galaxy)
    best_planet, best_planet_alts = pick_best_objs(all_dfs["planet"], all_alts["planet"], num_planet)
    best_point, best_point_alts = pick_best_objs(all_dfs["point"], all_alts["point"], num_point)

    if num_cluster > 0:
        print(f"Best clusters: {best_cluster}")
    if num_nebula > 0:
        print(f"Best nebula: {best_nebula}")
    if num_galaxy > 0:
        print(f"Best galaxy: {best_galaxy}")
    if num_planet > 0:
        print(f"Best planet: {best_planet}")
    if num_point > 0:
        print(f"Best point: {best_point}")
    print("=="*5)

    #list of object names
    chosen_objects = best_planet + best_cluster + best_nebula + best_galaxy + best_point
    #list of altitude trajectories
    chosen_alts = best_planet_alts + best_cluster_alts + best_nebula_alts + best_galaxy_alts + best_point_alts
    #list of chosen object types
    chosen_types =  ["planet"]*len(best_planet) + ["cluster"]*len(best_cluster) + ["nebula"]*len(best_nebula) + ["galaxy"]*len(best_galaxy) + ["point"]*len(best_point)

    ##NOW FIGURE OUT THE OPTIMAL ORDERING!

    #Build intervals
    intervals = []
    current_start = start_dt
    for _ in range(tot_objects):
        current_end = current_start + pd.Timedelta(minutes=minutes_per_target)
        intervals.append((current_start, current_end))
        current_start = current_end

    #Compute midpoints
    midpoints = [start + (end - start)/2 for start, end in intervals]
    time_local_datetimes = np.array([t.replace(tzinfo=None) for t in times.to_datetime(timezone=pacific)])

    if len(time_local_datetimes) != len(chosen_alts[0]):
        raise ValueError("Time array and altitude array do not have same length!")

    df_schedule = select_optimal_ordering(time_local_datetimes, 
                        intervals,
                        midpoints, 
                        chosen_objects, 
                        chosen_types,
                        chosen_alts, 
                        min_altitude=min_altitude)


    #print the observability links
    date_splits = date.split("-")
    for name_i in df_schedule["object"].tolist():
        print(create_observability_link(name_i, date_splits[2], date_splits[1], date_splits[0]))

    ##return stuff


    return_dict = {"time_local_datetimes": time_local_datetimes,
                    "best_cluster": best_cluster, "best_nebula": best_nebula, "best_planet": best_planet, "best_galaxy": best_galaxy, "best_point": best_point,
                    "df_schedule": df_schedule  }

    for class_i in object_classes:
        return_dict["df_" + class_i] = all_dfs[class_i]
        return_dict["alts_" + class_i] = all_alts[class_i]

    return return_dict










        