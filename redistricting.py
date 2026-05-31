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
        buffered = geom.buffer(100)  # 100 metrers buffer
        for j in sindex.intersection(buffered.bounds):
            if i != j and buffered.intersects(gdf.geometry[j]):
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

p_balance_wt = 1.0
contiguous_wt = 3.0

def get_components(district_tracts, adj):
    district_tracts=set(district_tracts)
    visited=set()
    components=[]
    for start in district_tracts:
        if start in visited:
            continue
        component=set()
        queue=[start]
        while queue:
            node=queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            queue.extend(adj[node]&(district_tracts-visited))
        components.append(component)
    return components

def is_contiguous_after_removal(tract, district_id, labels, adj):
    remaining=set(np.where(labels == district_id)[0]) - {tract}
    if len(remaining) <= 1:
        return True
    return len(get_components(remaining, adj)) == 1


def fix_all_contiguity(labels, adj, n):
    labels = labels.copy()
    changed = True
    while changed:
        changed = False
        for district in range(n):
            district_tracts = set(np.where(labels == district)[0])
            components = get_components(district_tracts, adj)
            if len(components) <= 1:
                continue
            largest = max(components, key=len)
            for component in components:
                if component is largest:
                    continue
                for tract in component:
                    neighbor_labels = [labels[j] for j in adj[tract] if labels[j] != district]
                    if neighbor_labels:
                        labels[tract] = max(set(neighbor_labels), key=neighbor_labels.count)
                        changed = True
                break
    return labels


def score_labels(labels, gdf, adj, n):
    population = gdf["population"].values
    centroids  = np.column_stack([gdf.geometry.centroid.x, gdf.geometry.centroid.y])

    total_dist = 0.0
    for d in range(n):
        members = np.where(labels == d)[0]
        if len(members) == 0:
            continue
        w = population[members]
        centre = np.average(centroids[members], axis=0, weights=w)
        total_dist += np.sum(np.linalg.norm(centroids[members] - centre, axis=1))
    compactness_score = total_dist / len(labels)

    district_pops = np.array([population[labels == d].sum() for d in range(n)])
    balance_score = district_pops.std() / district_pops.mean()

    return compactness_score, balance_score


def find_optimal_weights(gdf, adj, n, labels_init):
    coarse_grid = [
        (cw, bw)
        for cw in [1.0, 3.0, 5.0]
        for bw in [1.0, 3.0, 5.0]
    ]

    print("    Weight search: coarse grid...")
    coarse_results = []
    for cw, bw in coarse_grid:
        lbl = optimise(labels_init.copy(), gdf, adj, n, compact_wt=cw, balance_wt=bw)
        cs, bs = score_labels(lbl, gdf, adj, n)
        coarse_results.append((cw, bw, cs, bs, lbl))
        print(f"      CW={cw:.1f} BW={bw:.1f}  →  compactness={cs:,.0f}m  balance={bs:.4f}")

    all_cs = [r[2] for r in coarse_results]
    all_bs = [r[3] for r in coarse_results]
    cs_min, cs_max = min(all_cs), max(all_cs)
    bs_min, bs_max = min(all_bs), max(all_bs)

    def combined(cs, bs):
        norm_cs = (cs - cs_min) / (cs_max - cs_min + 1e-9)
        norm_bs = (bs - bs_min) / (bs_max - bs_min + 1e-9)
        return norm_cs + norm_bs

    coarse_results.sort(key=lambda r: combined(r[2], r[3]))
    best_cw, best_bw = coarse_results[0][0], coarse_results[0][1]
    print(f"    Best coarse: CW={best_cw} BW={best_bw}")

    step = 1.0
    fine_grid = [
        (max(0.5, best_cw + dcw), max(0.5, best_bw + dbw))
        for dcw in [-step, 0, step]
        for dbw in [-step, 0, step]
        if (dcw, dbw) != (0, 0)
    ]
    fine_grid = list(set(fine_grid))

    print("    Weight search: fine grid...")
    fine_results = list(coarse_results)
    for cw, bw in fine_grid:
        lbl = optimise(labels_init.copy(), gdf, adj, n, compact_wt=cw, balance_wt=bw)
        cs, bs = score_labels(lbl, gdf, adj, n)
        fine_results.append((cw, bw, cs, bs, lbl))
        print(f"      CW={cw:.1f} BW={bw:.1f} -> compactness={cs:,.0f}m  balance={bs:.4f}")

    all_cs = [r[2] for r in fine_results]
    all_bs = [r[3] for r in fine_results]
    cs_min, cs_max = min(all_cs), max(all_cs)
    bs_min, bs_max = min(all_bs), max(all_bs)
    fine_results.sort(key=lambda r: combined(r[2], r[3]))

    best_cw, best_bw, best_cs, best_bs, best_labels = fine_results[0]
    print(f"    ✓ Optimal weights: CW={best_cw} BW={best_bw}  "
          f"(compactness={best_cs:,.0f}m, balance={best_bs:.4f})")
    return best_cw, best_bw, best_labels


def optimise(labels, gdf, adj, n, compact_wt=3.0, balance_wt=1.0):
    labels = labels.copy()
    population = gdf["population"].values
    ideal = population.sum() / n
    centroids = np.column_stack([gdf.geometry.centroid.x, gdf.geometry.centroid.y])

    def district_centroid(d):
        members = np.where(labels == d)[0]
        w = population[members]
        return np.average(centroids[members], axis=0, weights=w)

    labels = fix_all_contiguity(labels, adj, n)

    all_centres  = np.array([district_centroid(d) for d in range(n)])
    typical_dist = np.mean([np.linalg.norm(all_centres[i] - all_centres[j])
                            for i in range(n) for j in range(i+1, n)])
    typical_dev  = (population.sum() / n) ** 2

    improved = True
    passes = 0
    while improved and passes < 50:
        improved = False
        passes  += 1
        tract_order = list(range(len(labels)))
        rng.shuffle(tract_order)

        for i in tract_order:
            current = labels[i]
            neighbor_districts = {labels[j] for j in adj[i] if labels[j] != current}
            if not neighbor_districts:
                continue
            if not is_contiguous_after_removal(i, current, labels, adj):
                continue

            current_pop = population[labels == current].sum()
            cur_centre = district_centroid(current)
            dist_to_current = np.linalg.norm(centroids[i] - cur_centre)
            best_score = 0.0
            best_target = None

            for target in neighbor_districts:
                target_pop = population[labels == target].sum()
                tgt_centre = district_centroid(target)
                dist_to_target = np.linalg.norm(centroids[i] - tgt_centre)

                compact_score = (dist_to_current - dist_to_target) / typical_dist

                before = (current_pop - ideal)**2 + (target_pop - ideal)**2
                after = ((current_pop - population[i]) - ideal)**2 + \
                                ((target_pop  + population[i]) - ideal)**2
                balance_score = (before - after) / typical_dev

                score = compact_wt * compact_score + balance_wt * balance_score
                if score > best_score:
                    best_score  = score
                    best_target = target

            if best_target is not None:
                labels[i] = best_target
                improved = True

        labels = fix_all_contiguity(labels, adj, n)

    return labels

# VISUALISATION :D (for now just the redistricted map)

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

    ax.set_title(f"{state}: {n} districts (optimised)", fontsize=13, fontweight="bold")
    ax.axis("off")
    plt.tight_layout()

    out = f"redistricting_output/{state.lower()}_optimised.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved as {out}")
    
    #had some help from nyla on how gepandas work
def plot_vote_share(state, gdf, labels, n):
    fig, ax = plt.subplots(figsize=(8, 8))
    
    #this is just the copy of the tract table to reuse it to plot this graph
    gdf = gdf.copy()
    gdf["label"] = labels
    
    # percentage votes by district for dems, and setting color map for rep=0
    district_votes = gdf.groupby("label")[["dem_votes", "rep_votes"]].sum()
    district_votes["dem_share"] = district_votes["dem_votes"] / (
        district_votes["dem_votes"] + district_votes["rep_votes"]
    )
    
    # colouring the district's dem share (blue = dem, red = rep)
    gdf["dem_share"] = gdf["label"].map(district_votes["dem_share"])
    gdf.plot(column="dem_share", cmap="RdBu", vmin=0, vmax=1,
             ax=ax, linewidth=0.1, edgecolor="white", legend=True)
    
    # district outlines uggh
    for d in range(n):
        union = unary_union(gdf.geometry[labels == d])
        gpd.GeoSeries([union]).plot(ax=ax, facecolor="none", edgecolor="white", linewidth=0.1)
    
    ax.set_title(f"{state}: District vote share (Blue=Dem, Red=Rep)", fontsize=13, fontweight="bold")
    ax.axis("off")
    plt.tight_layout()
    
    out = f"redistricting_output/{state.lower()}_voteshare.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved as {out}")
    
def plot_seat_comparison(state, gdf, labels, n):
    #again 
    gdf = gdf.copy()  
    gdf["label"] = labels
    
    #how many dems won and reps
    district_votes = gdf.groupby("label")[["dem_votes", "rep_votes"]].sum()
    redistricted_dem = (district_votes["dem_votes"] > district_votes["rep_votes"]).sum() 
    redistricted_rep = n - redistricted_dem
    
    #2020 results 
    actual = {
        "Alabama":       {"D": 1, "R": 6},
        "Massachusetts": {"D": 9, "R": 0},
        "Michigan":      {"D": 7, "R": 6},
    }
    actual_dem = actual[state]["D"]
    actual_rep = actual[state]["R"]
    
    fig, ax = plt.subplots(figsize=(6, 5))
    x = np.arange(2)
    width = 0.35
    #bar as comparison
    ax.bar(x[0] - width/2, actual_dem,       width, label="Actual 2020 (D)",       color="blue", alpha=0.5)
    ax.bar(x[1] - width/2, actual_rep,       width, label="Actual 2020 (R)",       color="red",  alpha=0.5)
    ax.bar(x[0] + width/2, redistricted_dem, width, label="Redistricted (D)", color="blue", alpha=1.0)
    ax.bar(x[1] + width/2, redistricted_rep, width, label="Redistricted (R)", color="red",  alpha=1.0)
    
    ax.set_xticks(x)
    ax.set_xticklabels(["Democrat seats", "Republican seats"])
    ax.set_ylabel("Number of seats")
    ax.set_title(f"{state}: Actual vs Redistricted seats", fontsize=13, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    
    out = f"redistricting_output/{state.lower()}_seat_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved as {out}")
    
def plot_population_balance(state, gdf, labels, n):
    gdf = gdf.copy()
    gdf["label"] = labels
    
    district_pop = gdf.groupby("label")["population"].sum()
    ideal = district_pop.sum() / n  # this is what every district should have
    
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(range(n), district_pop.values, color="steelblue", edgecolor="white")
    ax.axhline(ideal, color="red", linestyle="--", linewidth=1.5, label=f"Ideal ({ideal:,.0f})")
    
    ax.set_xlabel("District")
    ax.set_ylabel("Population (Millions)")
    ax.set_title(f"{state}: Population per district", fontsize=13, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    
    out = f"redistricting_output/{state.lower()}_population_balance.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved as {out}")

# ======
# (you guys can pretty much ignore this,, it just runs everything for each state in the config)

if __name__ == "__main__":
    for state, cfg in STATES.items():
        print(f"\n{'='*50}\n{state.upper()}\n{'='*50}")
        n = cfg["n_districts"]

        gdf, adj   = running(state, cfg)
        labels_init = initialise(gdf, n)

        print("  Finding optimal weights...")
        best_cw, best_bw, labels = find_optimal_weights(gdf, adj, n, labels_init)
        print(f"  Using CW={best_cw}, BW={best_bw} for {state}")

        plot_state(state, gdf, labels, n)
        plot_vote_share(state, gdf, labels, n)
        plot_seat_comparison(state, gdf, labels, n)
        plot_population_balance(state, gdf, labels, n)

        print(f"{state} Done.")
