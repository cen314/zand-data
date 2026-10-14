# Use this scraping code whenever you need to scrape single or multiple cells of your choice.

import os, math, json, time, random
import pandas as pd
import googlemaps
from dotenv import load_dotenv

# ==========================
# Config adapted from scraping_simple_grid.py
# ==========================

SEARCH_RADIUS_KM        = 1.2   # conceptual disk for density/coverage checks
CELL_RADIUS_KM          = 0.7   # max distance from cell center to include results (approx 1km² coverage)
                                 # Google API with rank_by=distance returns up to 20 places regardless of distance
                                 # This filter ensures we only keep places actually within our grid cell
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
GRID_FILE = "Scraping Codes (Google Maps)/grid_erbil.json"  # Your grid JSON file
CATEGORIES_FILE = "Scraping Codes (Google Maps)/Categories.xlsx"  # Your categories Excel file

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
    """Calculate distance in km between two lat/lng points"""
    (lat1, lng1), (lat2, lng2) = a, b
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    x = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2)
    return 2 * r * math.asin(math.sqrt(x))

def load_grid_data(filename):
    """Load grid data from JSON file"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_categories(filename):
    """Load categories from Excel file - reads Kurdish, English, Arabic columns"""
    df = pd.read_excel(filename)
    print(f"Available columns: {df.columns.tolist()}")
    categories = []
    for column in ['Kurdish', 'English', 'Arabic']:
        if column in df.columns:
            categories.extend(df[column].dropna().tolist())
    return list(set(categories))  # Remove duplicates

def find_grid_cell(grid_data, cell_label):
    """Find a specific grid cell by its label (e.g., 'M11')"""
    for cell in grid_data['grid_cells']:
        if cell['label'] == cell_label:
            return cell
    return None

def nearby_distance(pt, place_type=None, keyword=None, language=None, use_radius=False, radius_m=1000):
    """
    Single Nearby call with rank_by=distance (returns up to 20) or with radius.
    use_radius: if True, uses radius with rank_by=prominence instead of distance
    """
    params = {"location": pt}
    
    if use_radius:
        params["radius"] = radius_m
        # Don't set rank_by, defaults to prominence
    else:
        params["rank_by"] = "distance"
    
    if place_type:
        params["type"] = place_type
    if keyword:
        params["keyword"] = keyword
    if language:
        params["language"] = language
    
    # Must provide at least one of type/keyword/name
    if not (place_type or keyword):
        raise ValueError("nearby_distance requires type or keyword")
    
    try:
        res = gmaps.places_nearby(**params)
        return res.get('results', [])
    except Exception as e:
        print(f"Nearby error at {pt}: {e}")
        return []

def local_density(pt, seen_coords, radius_km=SEARCH_RADIUS_KM):
    """Calculate local density of already seen places"""
    if not seen_coords:
        return 0
    lat, lng = pt
    return sum(1 for (slat, slng) in seen_coords if hav_km((lat, lng), (slat, slng)) <= radius_km)

def save_state(cell_label, state):
    """Save scraping state for a specific cell"""
    path = os.path.join(STATE_DIR, f"state_cell_{cell_label}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f)

def load_state(cell_label):
    """Load scraping state for a specific cell"""
    path = os.path.join(STATE_DIR, f"state_cell_{cell_label}.json")
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# ==========================
# Main scraping function for a single cell
# ==========================

def scrape_grid_cell(grid_data, cell_label, max_calls=100, use_categories=False, filter_by_distance=True):
    """
    Scrape a specific grid cell using the same logic as scraping_simple_grid.py
    If use_categories=True, will use all categories from Categories.xlsx
    If filter_by_distance=True, only include results within CELL_RADIUS_KM of cell center
    """
    # Find the specific cell
    cell = find_grid_cell(grid_data, cell_label)
    if not cell:
        print(f"Cell {cell_label} not found in grid!")
        return [], 0
    
    print(f"=== Scraping Cell {cell_label} ===")
    print(f"Center: ({cell['center']['latitude']}, {cell['center']['longitude']})")
    print(f"Area: {cell['area_km2']}km²")
    
    # Load categories from Excel if requested
    if use_categories:
        categories = load_categories(CATEGORIES_FILE)
        print(f"Loaded {len(categories)} categories from Excel file")
    else:
        categories = None
    
    # Cell center point
    pt = (cell['center']['latitude'], cell['center']['longitude'])
    city_center = (grid_data['center_coordinates']['latitude'], 
                   grid_data['center_coordinates']['longitude'])
    
    # Load previous state (resume) or init
    state = load_state(cell_label) or {
        "seen_ids": [],
        "seen_coords": [],
        "rows": [],
        "calls": 0,
    }
    
    seen_ids = set(state["seen_ids"])
    seen_coords = [tuple(x) for x in state["seen_coords"]]
    rows = state["rows"]
    calls = int(state["calls"])
    
    def ingest(results, tag):
        """Process and store results from API calls"""
        new_ct = 0
        filtered_ct = 0
        for p in results:
            pid = p.get('place_id')
            if not pid or pid in seen_ids:
                continue
            bs = p.get('business_status')
            if bs and bs != 'OPERATIONAL':
                continue  # optional filter
            lat = p['geometry']['location']['lat']
            lng = p['geometry']['location']['lng']
            
            distance_from_cell = round(hav_km(pt, (lat, lng)), 2)
            
            # Filter by distance if enabled
            if filter_by_distance and distance_from_cell > CELL_RADIUS_KM:
                filtered_ct += 1
                continue
            
            rows.append({
                'place_id': pid,
                'name': p.get('name'),
                'address': p.get('vicinity') or p.get('formatted_address'),
                'cell_label': cell_label,
                'lat': lat,
                'lng': lng,
                'distance_from_cell_center_km': distance_from_cell,
                'distance_from_city_center_km': round(hav_km(city_center, (lat, lng)), 2),
                'types': p.get('types'),
                'rating': p.get('rating'),
                'user_ratings_total': p.get('user_ratings_total'),
                'price_level': p.get('price_level'),
                'tag': tag,
            })
            seen_ids.add(pid)
            seen_coords.append((lat, lng))
            new_ct += 1
        
        if filtered_ct > 0:
            print(f"      Filtered out {filtered_ct} places beyond {CELL_RADIUS_KM}km radius")
        return new_ct
    
    # Choose between standard approach or comprehensive category search
    if use_categories and categories:
        # Use all categories from Excel file
        print(f"  Using comprehensive category search with {len(categories)} categories...")
        category_count = 0
        for category in categories:
            if calls >= max_calls:
                break
            # Try as keyword first (better for multilingual terms)
            try:
                print(f"    Searching for '{category}' as keyword...")
                res = nearby_distance(pt, keyword=category)
                calls += 1
                new_count = ingest(res, tag=f'CAT:{category}')
                print(f"      Found {new_count} new places")
                category_count += 1
                
                # Small delay to respect API limits
                if category_count % 10 == 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"      Error searching for '{category}': {e}")
                continue
    else:
        # Same three-tier approach as scraping_simple_grid.py
        
        # Tier A — always; guarantees coverage
        if calls < max_calls:
            print(f"  Tier A: restaurant search...")
            resA = nearby_distance(pt, place_type='restaurant')
            calls += 1
            newA = ingest(resA, tag='A:restaurant')
            print(f"    Found {newA} new restaurants")
        else:
            newA = 0
        
        # Tier B — backup type if sparse
        if calls < max_calls and newA < NEW_SPARSE_THRESHOLD:
            # Use first backup type for simplicity
            btype = BACKUP_TYPES[0]
            print(f"  Tier B: {btype} search (sparse area)...")
            resB = nearby_distance(pt, place_type=btype)
            calls += 1
            newB = ingest(resB, tag=f'B:{btype}')
            print(f"    Found {newB} new {btype} places")
        else:
            newB = 0
        
        # Tier C — keyword anchors unless very dense
        dense = local_density(pt, seen_coords, radius_km=SEARCH_RADIUS_KM) >= LOCAL_DENSITY_THRESHOLD
        if calls < max_calls and not dense:
            print(f"  Tier C: keyword anchor searches...")
            for kw, lang in ANCHOR_KEYWORDS:
                if calls >= max_calls:
                    break
                print(f"    Searching for '{kw}' in {lang}...")
                resC = nearby_distance(pt, keyword=kw, language=lang)
                calls += 1
                newC = ingest(resC, tag=f'C:{kw}')
                print(f"      Found {newC} new places")
    
    # Save final state
    save_state(cell_label, {
        "seen_ids": list(seen_ids),
        "seen_coords": [list(x) for x in seen_coords],
        "rows": rows,
        "calls": calls,
    })
    
    print(f"Cell {cell_label}: {len(rows)} total places, {calls} API calls used")
    return rows, calls

# ==========================
# Main execution function
# ==========================

def scrape_specific_cells(cell_labels, max_calls_per_cell=100, use_categories=False, filter_by_distance=True):
    """
    Scrape specific grid cells
    cell_labels: list of cell labels like ['M11', 'N12'] or single string 'M11'
    use_categories: if True, uses all 170+ categories from Categories.xlsx
    filter_by_distance: if True, only includes results within CELL_RADIUS_KM of cell center
    """
    if isinstance(cell_labels, str):
        cell_labels = [cell_labels]
    
    # Load grid data
    grid_data = load_grid_data(GRID_FILE)
    print(f"Loaded grid: {grid_data['city']} with {grid_data['grid_info']['total_cells']} cells")
    
    if use_categories:
        print(f"🔍 COMPREHENSIVE MODE: Will use all categories from Categories.xlsx")
    else:
        print(f"⚡ STANDARD MODE: Using optimized 3-tier approach")
    
    all_rows = []
    total_calls = 0
    
    for cell_label in cell_labels:
        rows, calls = scrape_grid_cell(grid_data, cell_label, max_calls_per_cell, use_categories, filter_by_distance)
        all_rows.extend(rows)
        total_calls += calls
        
        # Small delay between cells to be respectful to the API
        if len(cell_labels) > 1:
            time.sleep(1)
    
    # Save results to Excel
    if all_rows:
        df = pd.DataFrame(all_rows)
        df = df.drop_duplicates('place_id')  # Remove any duplicates
        
        output_file = f"scraped_cells_{'_'.join(cell_labels)}.xlsx"
        df.to_excel(output_file, index=False)
        print(f"\n=== RESULTS ===")
        print(f"Saved {len(df)} unique places to {output_file}")
        print(f"Total API calls used: {total_calls}")
        print(f"Cells scraped: {', '.join(cell_labels)}")
        
        # Show summary by cell
        if len(cell_labels) > 1:
            cell_summary = df.groupby('cell_label').size()
            print(f"\nPlaces per cell:")
            for cell, count in cell_summary.items():
                print(f"  {cell}: {count} places")
    else:
        print("No places found in the specified cells.")

# ==========================
# Example usage
# ==========================

if __name__ == "__main__":
    # Use ALL 170+ categories from Categories.xlsx (comprehensive search)
    # filter_by_distance=True ensures only places within 0.7km of cell center are included
    scrape_specific_cells("L7", max_calls_per_cell=500, use_categories=True, filter_by_distance=True)
    
    # Alternative: Standard approach (fast, 3-5 calls) - uncomment if you prefer this
    # scrape_specific_cells("M11", max_calls_per_cell=50, use_categories=False, filter_by_distance=True)
    
    # Example: Scrape without distance filtering (will include all results from API)
    # scrape_specific_cells("M11", max_calls_per_cell=200, use_categories=True, filter_by_distance=False)
    
    # Example: Scrape multiple cells with comprehensive categories
    # scrape_specific_cells(["M11", "M12", "N11", "N12"], max_calls_per_cell=200, use_categories=True)
    
    # Example: Scrape area with comprehensive categories (WARNING: MANY API calls!)
    # area_cells = ["L10", "L11", "L12", "M10", "M11", "M12", "N10", "N11", "N12"]
    # scrape_specific_cells(area_cells, max_calls_per_cell=200, use_categories=True)
