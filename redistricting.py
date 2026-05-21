# okay before eveyrthing a lot of the inspo behind this was from GerryChain :p
# they basically did what we wnated to but like more professionally with a LOT more features soo
# also we gotta acknolwedge that ai (claude) was used to debug and esssentially rewrite some stuff cus i did it horribly wrong (i shall mention the bits when they come)

import os # for file handling on the system 
import numpy as np
import pandas as pd
import geopandas as gpd # reads shapefiloes (the thing we're using)
import matplotlib.pyplot as plt
import requests # makes web req,, we use to call APIs (for census poopulation info)
from shapely.ops import unary_union # for merging the smol smol tracts into big boi districts
from collections import defaultdict # this is just a very convinient lil guy for making adjecency graphs. like, if smthg doesnt exist, it'lll just automatically make a new empty set for it
import warnings # look down
warnings.filterwarnings("ignore") # these two together just to hide a bunch of ugly warnigns that no one cares abt :D (learnt from experience that this is okay lmao)

## CONFIG 

# this is where we're makig our list of states
# fips is the official US government ID (in the data we downloaded)
# n_districts is just how many districts we wanna split the state into (can change but this is what is currently being used)
# precinct is the patht to the shapefile for each precinct level voting results. for majkign coparision visulisations later ***IMPORTANT FOR SAMI JUAN ALYSSA***
STATES = {
    "Alabama":       {"fips": "01", "n_districts": 7,  "precinct": "al_2020/al_2020.shp"},
    "Massachusetts": {"fips": "25", "n_districts": 9,  "precinct": "ma_2020/ma_2020.shp"},
    "Michigan":      {"fips": "26", "n_districts": 13, "precinct": "mi_2020/mi_2020.shp"},
}

# i later found out that the population data isnt even there in the data we downloaded (big L) so gotta get it from the official api which is cooler so ayyyy
CENSUS_API_KEY = "acbd3dd705c92718bc0fd403a7fae285ab678923"
# the total population variable in the api is saved as P1_001N (idk why its such a weird name but :D)
# making a variable incase we need to change it (i dont trust apis :/)
CENSUS_VAR = "P1_001N"

# okay so, this is kinda cheating? but basically all you need to understand is that since kmean is suposed to be random at the start, if i run it once and then run it again the two results will be different. soo, instead we just seed some random numbers and use thsoe same random numbers again and again so its still kmeans but we can like write a report lmao
rng = np.random.default_rng(134340)

# created that o/p folder to save the visulisations in
os.makedirs("redistricting_output", exist_ok=True)

## DATA INGESTION ==========

# as the fn says, its loading the shapefile.
# the i/p param is the fips code for that state
def load_shapefile(fips):
    gdf  = gpd.read_file(f"tl_2020_{fips}_tract.shp") #asking geopandas to read the shapefile and turn it into a geodataframe (which is like a pandas dataframe but with geometry info)
    
    # this stuff is cleaning the data and making sure its in the right format
    # (you can pretty much assume any cleaning-up-data work had claude help, ive nvr done it before)

    # thius little block idk what it does exactaly but i just put it and it works so yay
    # what i understood is that the data is so unclean that coord ref is just missing, so we gotta set it and then again convert it
    # idk why we cant just set it right in the first place but when i tried it thru an errorr
    # i prob did it wrong but this works so im not gonna meddle with it anymore
    # (same crisis in the precinct file, lmao (you'll see it later :p))
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    gdf = gdf.to_crs(epsg=5070)
    gdf["GEOID"] = gdf["GEOID"].astype(str)

    return gdf
    # also, all of this is basic convention. like, you find this code in pretty much every geodata procesing script so i just took it from there :p
    # gdf looks like:
    # columns: GEOID, geometry, ALAND (other cols too but we dont care abt them)

# okay, so some bg info:
# turns out, our data doesnt have population info for each of the tracts (very big bad)
# i think one exists where they come together but its like such a big file and i already had a headache finidng this nonsesne so :/
# BUT the US census has an API where you can call the poopulation data for each tract :DD
# i went and requested an API key (which was there at the top in config) and then wrote this fn to call the api ad get the pop data
def fetch_population(fips):
    # builfing the url to call the census api
    url = (
        f"https://api.census.gov/data/2020/dec/pl"
        f"?get={CENSUS_VAR},GEO_ID&for=tract:*&in=state:{fips}"
        + (f"&key={CENSUS_API_KEY}")
    )

    # you guys havnt learnt abt the try except block yet, but its part of error handling
    # apis need a LOT of error handling
    # they suck
    # can you tell i hate usiing apis? because i DO they SUCK

    # but pretty much this whole block below is just trying to call the api and if it works, great, we get the data :D
    # but if it doesnt work (which is very likely >:((( ) then instead of crashing the whole program, we just catch the error and print a message and then return None 
    # later on we can check if we got the data or not and decide what to do (in this case, we're just gonna use a proxy based on land area which is not ideal but better than nothing)
    # claude helped a lot with this (error handling also you can assume claude helped with)
    # idk how to test if the api call works properly so claude to the rescue :D
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()

        rows = r.json()
        if isinstance(rows, dict):
            print(f" Census API error response: {rows}")
            return None
        df = pd.DataFrame(rows[1:], columns=rows[0])
        df["GEOID"] = df["GEO_ID"].str.replace("1400000US", "") # the GEO_ID comes with this weird prefix that we dont need, so just removing it (to match the shapefiles we already have TT)
        df["population"] = pd.to_numeric(df[CENSUS_VAR])
        print(f"  Census API: loaded {len(df)} tracts.")
        return df[["GEOID", "population"]]
    except Exception as e:
        print(f" Census API not working (suprise suprise),, using ALAND instead :p")
        return None

# loads the Harvard Dataverse shapefile which has precinct boundaries and real 2020 vote counts (the stuff in the al_202, ma_2020, mi_2020 folders)
def load_precinct_votes(precinct_path):
    precinct = gpd.read_file(precinct_path)
    # thius little block idk what it does exactaly but i just put it and it works so yay
    # what i understood is that the data is so unclean that coord ref is just missing, so we gotta set it and then again convert it
    # idk why we cant just set it right in the first place but when i tried it thru an errorr
    # i prob did it wrong but this works so im not gonna meddle with it anymore
    if precinct.crs is None: 
        precinct = precinct.set_crs(epsg=4326)
    precinct = precinct.to_crs(epsg=5070)

    d_col = next((v for v in precinct.columns if "PRED" in v.upper()), None) # votes for G20PRED (Biden)
    r_col = next((v for v in precinct.columns if "PRER" in v.upper()), None) # votes for G20PRER (Trump)
    if not d_col or not r_col:
        raise ValueError("D:")

    # cleaning up the vote coutns
    # making sure they are numbers (to_numberic)
    # if smthg doesnt have a vaule, with just fill it w/ 0 (fillna(0))
    precinct["dem_votes"] = pd.to_numeric(precinct[d_col], errors="coerce").fillna(0) 
    precinct["rep_votes"] = pd.to_numeric(precinct[r_col], errors="coerce").fillna(0) 
    return precinct[["geometry", "dem_votes", "rep_votes"]]
    # precinct looks like:
    # columns: geometry, dem_votes, rep_votes

# this is specifically for the bar chart comparing the redistricted D/R seats vs actual 2020 results
# to make it easier basically this just assigns the votes to the tracts based on which precinct centroid falls within which tract, and then summing up the votes for each tract
# its a spacial join (sjoin) so all i had to do was copy paste and change some stuff from the geopandas documentation :D
def assign_votes_to_tracts(gdf, precinct):
    precinct_pts = precinct.copy()
    precinct_pts["geometry"] = precinct.geometry.centroid
    joined = gpd.sjoin(precinct_pts, gdf[["geometry"]], how="left", predicate="within")
    vote_by_tract = joined.groupby("index_right")[["dem_votes", "rep_votes"]].sum()
    gdf = gdf.copy()
    gdf["dem_votes"] = vote_by_tract.reindex(gdf.index)["dem_votes"].fillna(0)
    gdf["rep_votes"] = vote_by_tract.reindex(gdf.index)["rep_votes"].fillna(0)
    return gdf
    # now, gdf looks like:
    # columns: GEOID, geometry, ALAND, dem_votes, rep_votes

def build_adjacency(gdf):
    adj = defaultdict(set)
    sindex = gdf.sindex # spacial index (so we can chk tracts near the tract we're looking at)
    for i, geom in enumerate(gdf.geometry):
        for j in sindex.intersection(geom.bounds):
            if i != j and geom.touches(gdf.geometry[j]):
                adj[i].add(j)
                adj[j].add(i)
    return adj
    # adj looks like:
    # { 0: {p, q, r}, 1: {t, k, r}, ... }
    # here, tract p, q, r border tract 0

# Runs all the above steps in order and returns gdf (the tract table with population + votes) and adj (the adjacency graph)
# just a lil inbetween fn to call all the fn to make the code cleaner in the main block (at the bottom)
def running(state, cfg):
    fips = cfg["fips"]
    gdf = load_shapefile(fips) # loading file (calling that fn)

    # this blow adds a population col to the gdf
    pop_df = fetch_population(fips) # fetching population 
    if pop_df is not None: # in case the api call fail (IT ALWAYS DOES)
        gdf = gdf.merge(pop_df, on="GEOID", how="left")
        gdf["population"] = gdf["population"].fillna(gdf["population"].median())
    else:
        gdf["population"] = (gdf["ALAND"] / gdf["ALAND"].sum() * 1e6).round().astype(int)

    precinct = load_precinct_votes(cfg["precinct"]) # calling that load_precinct_votes fn to get the precinct level vote counts and geometries
    gdf = assign_votes_to_tracts(gdf, precinct) # calling that fn to assign the vots to their respective tracts

    adj = build_adjacency(gdf) # building the ag

    return gdf, adj
    # now, gdf looks like:
    # columns: GEOID, geometry, ALAND, population, dem_votes, rep_votes

# INITIALISATION  (augmented kmeans seeding :DD)

def initialise(gdf, n):
    # gets the centers of each tract and puts in an array
    centroids = np.column_stack([gdf.geometry.centroid.x, gdf.geometry.centroid.y])

    # kmeans seed selection
    seeds = [rng.integers(len(gdf))] # startinf w/ random seed (remeber that rng we made in config? its that :D so its random yes, but same random every time lmao)
    # this is the kmeans++ seeding method (common solution), which is a way to choose the initial seeds for kmeans in a way that they are spread out and not clumped together (which can lead to better results)
    # not my brainchild, already exists just had to put it in here
    for _ in range(n - 1):
        dists = np.min(
            [np.linalg.norm(centroids - centroids[s], axis=1) for s in seeds], axis=0
        )
        probs = dists ** 2 / (dists ** 2).sum()
        seeds.append(rng.choice(len(gdf), p=probs))

    # assigning each tract to nearest seed
    labels = np.argmin(
        np.column_stack([np.linalg.norm(centroids - centroids[s], axis=1) for s in seeds]),
        axis=1,
    )
    return labels
    # labels looks like:
    # [d1, d2, d2, d3 ...]
    # where track 0 is in d1, track 1 in d2 and so on

# OPTIMISATION (blamk rn) =====

def optimise(labels, gdf, adj, n): # gege add whatever you need here
    # gege do stuff here :D
    return labels

# VISUALISATION :D (for now just the redistricted map) ======

# this is just a function to plot the state with the new districts (after optimising)
# this is pretty self explainatory so im not gonna yap again
def plot_state(state, gdf, labels, n):
    fig, ax = plt.subplots(figsize=(8, 8))

    cmap = plt.get_cmap("tab20", n)
    colors = [cmap(labels[i]) for i in range(len(gdf))]
    gdf.plot(color=colors, ax=ax, linewidth=0.1, edgecolor="white")

    # district outlines
    for d in range(n):
        union = unary_union(gdf.geometry[labels == d])
        gpd.GeoSeries([union]).plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.2)

    ax.set_title(f"{state}: {n} districts (unoptimised (rn))", fontsize=13, fontweight="bold")
    ax.axis("off")
    plt.tight_layout()

    out = f"redistricting_output/{state.lower()}_unoptimised.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved as {out}")

# you guys need to plot the figures here:






# ======
# (you guys can pretty much ignore this,, it just runs everything for each state in the config)

if __name__ == "__main__":
    for state, cfg in STATES.items():
        print(f"\n{'='*50}\n{state.upper()}\n{'='*50}") # to make a cool header for each state
        n = cfg["n_districts"] # go up to the config to understand this (very self explainatory)

        gdf, adj = running(state, cfg)
        labels = initialise(gdf, n)
        labels = optimise(labels, gdf, adj, n)
        plot_state(state, gdf, labels, n) # so like, after the optimisation fn is filled in the plots i made will reflect it :D

        print(f"[{state}] Done.")