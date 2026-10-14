# This is a good and efficient code for scraping a grid of a city automatically created by the code.

import os, math, json, time, random
import pandas as pd
import googlemaps
from dotenv import load_dotenv

# ==========================
# Config (tuned for KRI)
# ==========================
CITIES = {
    "Erbil":        {"center": (36.219155, 44.038233), "radius_km": 16},
    # "Sulaymaniyah": {"center": (35.5571, 45.4356),     "radius_km": 14},
}

SEARCH_RADIUS_KM        = 1.2   # conceptual disk for density/coverage checks
STEP_KM                 = 1.6   # tile spacing (<= SEARCH_RADIUS_KM * sqrt(2))
ANCHOR_EVERY            = 4     # every Nth tile, run keyword anchors
NEW_SPARSE_THRESHOLD    = 6     # if Tier A returns <6 new places → do Tier B once
LOCAL_DENSITY_THRESHOLD = 25    # high-density threshold to suppress extra calls
MAX_CALLS_PER_RUN       = 1500  # budget cap per run (~$52 at list price)

BACKUP_TYPES = ['cafe', 'bakery', 'meal_takeaway', 'food']  # rotated on sparse/edge tiles
ANCHOR_KEYWORDS = [
    ("restaurant", "en"),   # English anchor
    ("مطعم",       "ar"),   # Arabic anchor
    ("خواردنگە",   "ar"),   # Kurdish term often indexed under 'ar' locale
]

STATE_DIR = "./scrape_state"
OUTPUT_XLSX = f"Kurdistan_places_grid.xlsx"

# ==========================
# Setup
# ==========================
load_dotenv()
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("Missing API_KEY in environment or .env file")

os.makedirs(STATE_DIR, exist_ok=True)

gmaps = googlemaps.Client(key=API_KEY)

# ==========================
# Helpers
# ==========================

def hav_km(a, b):
    (lat1, lng1), (lat2, lng2) = a, b
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    x = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2)
    return 2 * r * math.asin(math.sqrt(x))


def make_grid(center, radius_km, step_km):
    """Deterministic row-major grid; each point is tagged with is_edge."""
    lat, lng = center
    dlat = step_km / 111.0
    dlng = step_km / (111.0 * math.cos(math.radians(lat)))

    lat_min, lat_max = lat - radius_km/111.0, lat + radius_km/111.0
    lng_min, lng_max = lng - radius_km/(111.0*math.cos(math.radians(lat))), lng + radius_km/(111.0*math.cos(math.radians(lat)))

    tiles = []
    i = 0
    row = lat_min
    while row <= lat_max + 1e-9:
        col = lng_min
        while col <= lng_max + 1e-9:
            p = (row, col)
            if hav_km(center, p) <= radius_km:
                is_edge = (hav_km(center, p) >= 0.85 * radius_km)  # 85% ring outward
                tiles.append({"pt": p, "is_edge": is_edge, "idx": i})
            i += 1
            col += dlng
        row += dlat
    return tiles


def nearby_distance(pt, place_type=None, keyword=None, language=None):
    """Single Nearby call with rank_by=distance (returns up to 20)."""
    params = {"location": pt, "rank_by": "distance"}
    if place_type:
        params["type"] = place_type
    if keyword:
        params["keyword"] = keyword
    if language:
        params["language"] = language
    # Must provide at least one of type/keyword/name with rank_by=distance
    if not (place_type or keyword):
        raise ValueError("nearby_distance requires type or keyword when rank_by=distance")
    try:
        res = gmaps.places_nearby(**params)
        return res.get('results', [])
    except Exception as e:
        print(f"Nearby error at {pt}: {e}")
        return []


def local_density(pt, seen_coords, radius_km=SEARCH_RADIUS_KM):
    if not seen_coords:
        return 0
    lat, lng = pt
    # simple brute-force count; fast enough at city scale
    return sum(1 for (slat, slng) in seen_coords if hav_km((lat, lng), (slat, slng)) <= radius_km)


def save_state(city, state):
    path = os.path.join(STATE_DIR, f"state_{city}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f)


def load_state(city):
    path = os.path.join(STATE_DIR, f"state_{city}.json")
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# ==========================
# Main per-city runner
# ==========================

def run_city(city, center, radius_km, max_calls=MAX_CALLS_PER_RUN):
    tiles = make_grid(center, radius_km, STEP_KM)

    # Load previous state (resume) or init
    state = load_state(city) or {
        "cursor": 0,
        "seen_ids": [],
        "seen_coords": [],   # list of (lat, lng) aligned with seen_ids
        "rows": [],
        "calls": 0,
    }

    seen_ids = set(state["seen_ids"])  # for fast lookup
    seen_coords = [tuple(x) for x in state["seen_coords"]]
    rows = state["rows"]
    cursor = int(state["cursor"]) if state["cursor"] < len(tiles) else 0
    calls = int(state["calls"]) if state["calls"] <= max_calls else 0

    def ingest(results, tag):
        new_ct = 0
        for p in results:
            pid = p.get('place_id')
            if not pid or pid in seen_ids:
                continue
            bs = p.get('business_status')
            if bs and bs != 'OPERATIONAL':
                continue  # optional filter
            lat = p['geometry']['location']['lat']
            lng = p['geometry']['location']['lng']
            if hav_km(center, (lat, lng)) > radius_km:
                continue
            rows.append({
                'place_id': pid,
                'name': p.get('name'),
                'address': p.get('vicinity') or p.get('formatted_address'),
                'city': city,
                'lat': lat,
                'lng': lng,
                'distance_km': round(hav_km(center, (lat, lng)), 2),
                'types': p.get('types'),
                'rating': p.get('rating'),
                'user_ratings_total': p.get('user_ratings_total'),
                'price_level': p.get('price_level'),
                'tag': tag,
            })
            seen_ids.add(pid)
            seen_coords.append((lat, lng))
            new_ct += 1
        return new_ct

    # Deterministic order; one Tier-A call always, extras are conditional
    i = cursor
    while i < len(tiles) and calls < max_calls:
        tile = tiles[i]
        pt = tile['pt']
        is_edge = tile['is_edge']

        # Tier A — always; guarantees coverage
        resA = nearby_distance(pt, place_type='restaurant')
        calls += 1
        newA = ingest(resA, tag='A:restaurant')

        # Decide on Tier B (backup type) only if sparse or edge
        if newA < NEW_SPARSE_THRESHOLD or is_edge:
            # rotate backup types by tile index
            btype = BACKUP_TYPES[i % len(BACKUP_TYPES)]
            resB = nearby_distance(pt, place_type=btype)
            calls += 1
            newB = ingest(resB, tag=f'B:{btype}')
        else:
            newB = 0

        # Decide on Tier C (keyword anchors) every Nth tile, unless very dense
        dense = local_density(pt, seen_coords, radius_km=SEARCH_RADIUS_KM) >= LOCAL_DENSITY_THRESHOLD
        if (i % ANCHOR_EVERY == 0) and not dense:
            for kw, lang in ANCHOR_KEYWORDS:
                resC = nearby_distance(pt, keyword=kw, language=lang)
                calls += 1
                _ = ingest(resC, tag=f'C:{kw}')
                if calls >= max_calls:
                    break

        # Periodic checkpoint
        if (i - cursor) % 25 == 0 or calls >= max_calls:
            save_state(city, {
                "cursor": i + 1,
                "seen_ids": list(seen_ids),
                "seen_coords": [list(x) for x in seen_coords],
                "rows": rows,
                "calls": calls,
            })
        i += 1

    # Final checkpoint
    save_state(city, {
        "cursor": i,
        "seen_ids": list(seen_ids),
        "seen_coords": [list(x) for x in seen_coords],
        "rows": rows,
        "calls": calls,
    })

    return rows, calls, i, len(tiles)

# ==========================
# Run all cities & write
# ==========================
all_rows = []
spent_calls = 0

for city, cfg in CITIES.items():
    print(f"=== Running {city} ===")
    rows, calls, idx, total = run_city(city, cfg['center'], cfg['radius_km'])
    print(f"{city}: {len(rows)} rows accumulated, calls this run={calls}, progress={idx}/{total}")
    all_rows.extend(rows)
    spent_calls += calls

# Dedup across cities just in case (place_id is global)
df = pd.DataFrame(all_rows)
if not df.empty:
    df = df.drop_duplicates('place_id')
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"Saved {len(df)} unique places to {OUTPUT_XLSX}. Total calls this run: {spent_calls}")
else:
    print("No rows collected in this run.")