import osmnx as ox
import pandas as pd
import os
import time
from tqdm import tqdm
from shapely.geometry import Point, Polygon, MultiPolygon  # type hints only
from openpyxl import load_workbook
import re

print("🔍 Starting OpenStreetMap data collection...")
start_time = time.time()

# 1️⃣  List of places --> (Overpass place name, Kurdish city label)
places = [
    # ("Sulaymaniyah, Iraq", "Slemani"),
    ("Erbil, Iraq",        "Hawler"),   # Kurdish name for Erbil
    # ("Basra, Iraq",        "Basra"),
    # ("Baghdad, Iraq",      "Baghdad"),
    # ("Duhok, Iraq",        "Duhok"),
]

# Load search terms from Excel file
def load_search_terms(excel_path, sheet_name='Markets', skip_rows=1):
    """Load search terms from the specified sheet in Categories Excel file"""
    try:
        # Read the Markets sheet, skipping the first row (header)
        categories_df = pd.read_excel(excel_path, sheet_name=sheet_name, skiprows=skip_rows)
        search_terms = []
        
        # Combine all language columns into a single list of search terms
        for _, row in categories_df.iterrows():
            for col in ['English', 'Kurdish', 'Arabic']:
                if pd.notna(row[col]) and str(row[col]).strip():
                    search_terms.append(str(row[col]).strip())
        
        # Remove duplicates while preserving order
        search_terms = list(dict.fromkeys(search_terms))
        print(f"📋 Loaded {len(search_terms)} market search terms from {sheet_name} sheet (skipped first {skip_rows} row(s))")
        return search_terms
    except Exception as e:
        print(f"⚠️  Warning: Could not load search terms from {excel_path}, sheet '{sheet_name}': {e}")
        return []

# Load search terms from Markets sheet, skipping the first row
search_terms = load_search_terms("Scraping Codes (Google Maps)/Categories.xlsx", sheet_name='Markets', skip_rows=1)

# 2️⃣  Define tags for amenity-based search (only marketplace)
amenity_tags = {
    "amenity": [ 
        "marketplace"
    ]
}

# 3️⃣  Functions for different search types
def search_by_amenities(place, city_label, tags):
    """Search for locations by amenity/shop tags"""
    locations = []
    try:
        gdf = ox.features_from_place(place, tags)
        
        for _, row in gdf.iterrows():
            geom = row.get("geometry")
            if geom is None:
                continue

            lon, lat = geom.centroid.x, geom.centroid.y
            
            record = {
                "City": city_label,
                "Search_Type": "amenity",
                "Amenity": row.get("amenity", row.get("shop", "")),
                "Latitude": lat,
                "Longitude": lon,
            }

            # Copy all other non-NaN tags
            for col, val in row.items():
                if col == "geometry" or pd.isna(val):
                    continue
                if col in record:
                    continue
                record[col] = str(val)

            locations.append(record)
            
    except Exception as e:
        print(f"⚠️  Amenity search error for {city_label}: {str(e)}")
    
    return locations

def search_by_name_terms(place, city_label, search_terms):
    """Search for locations by name using search terms"""
    locations = []
    
    # Get the boundary of the place for spatial filtering
    try:
        boundary = ox.geocode_to_gdf(place)
        
        # Create a more flexible query that searches for any POI with names
        # matching our search terms
        name_tags = {"name": True}  # Get all features with names
        
        gdf = ox.features_from_place(place, name_tags)
        
        # Filter results based on name matching our search terms
        for _, row in gdf.iterrows():
            name = row.get("name", "")
            if not name or pd.isna(name):
                continue
                
            name_str = str(name).lower()
            
            # Check if any search term matches the name
            matched_term = None
            for term in search_terms:
                if term.lower() in name_str or name_str in term.lower():
                    matched_term = term
                    break
            
            if matched_term:
                geom = row.get("geometry")
                if geom is None:
                    continue

                lon, lat = geom.centroid.x, geom.centroid.y
                
                record = {
                    "City": city_label,
                    "Search_Type": "name",
                    "Matched_Term": matched_term,
                    "Amenity": row.get("amenity", row.get("shop", "")),
                    "Latitude": lat,
                    "Longitude": lon,
                }

                # Copy all other non-NaN tags
                for col, val in row.items():
                    if col == "geometry" or pd.isna(val):
                        continue
                    if col in record:
                        continue
                    record[col] = str(val)

                locations.append(record)
                
    except Exception as e:
        print(f"⚠️  Name search error for {city_label}: {str(e)}")
    
    return locations

# 4️⃣  Main data collection
records = []

# Progress bar for cities
for place, city_label in tqdm(places, desc="Processing cities", unit="city"):
    print(f"\n📍 Fetching data for {city_label}...")
    city_start_time = time.time()
    
    city_records = []
    
    # Search by amenities
    print(f"🏪 Searching by amenities in {city_label}...")
    amenity_locations = search_by_amenities(place, city_label, amenity_tags)
    city_records.extend(amenity_locations)
    print(f"   Found {len(amenity_locations)} amenity-based locations")
    
    # Search by name terms (if we have search terms loaded)
    if search_terms:
        print(f"🔍 Searching by name terms in {city_label}...")
        name_locations = search_by_name_terms(place, city_label, search_terms)
        city_records.extend(name_locations)
        print(f"   Found {len(name_locations)} name-based locations")
    
    records.extend(city_records)
    
    city_time = time.time() - city_start_time
    print(f"✅ Total found in {city_label}: {len(city_records)} locations")
    print(f"⏱️  Time taken: {city_time:.2f} seconds")

# 5️⃣  DataFrame with preferred column order
print("\n📊 Creating DataFrame and organizing columns...")
df = pd.DataFrame(records)

if len(df) > 0:
    # Define core columns in preferred order
    core_cols = ["name", "Search_Type", "Matched_Term", "Amenity", "City", "Latitude", "Longitude"]
    # Only include core columns that exist in the dataframe
    existing_core_cols = [col for col in core_cols if col in df.columns]
    other_cols = [c for c in df.columns if c not in existing_core_cols]
    df = df[existing_core_cols + other_cols]
    
    # Remove duplicate locations (same lat/lon)
    initial_count = len(df)
    df = df.drop_duplicates(subset=['Latitude', 'Longitude'], keep='first')
    final_count = len(df)
    if initial_count > final_count:
        print(f"🔄 Removed {initial_count - final_count} duplicate locations")
else:
    print("⚠️  No locations found!")

# 6️⃣  Write results to Excel
output_path = "./OSM_markets_enhanced.xlsx"
print(f"\n💾 Saving data to {output_path}...")

if len(df) > 0:
    if os.path.exists(output_path):
        with pd.ExcelWriter(output_path, engine="openpyxl",
                            mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name="OSM_Combined_Results", index=False)
    else:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="OSM_Combined_Results", index=False)
    
    # Create summary statistics
    summary_stats = []
    if 'Search_Type' in df.columns:
        search_type_counts = df['Search_Type'].value_counts()
        for search_type, count in search_type_counts.items():
            summary_stats.append(f"  - {search_type.title()}-based: {count:,} locations")
    
    total_time = time.time() - start_time
    print(f"\n✅ Done! Summary:")
    print(f"Total locations found: {len(df):,}")
    if summary_stats:
        print("Breakdown by search type:")
        for stat in summary_stats:
            print(stat)
    print(f"Total time taken: {total_time:.2f} seconds")
    print(f"Results saved to: {output_path} (sheet 'OSM_Combined_Results')")
else:
    print(f"\n❌ No locations found to save!")
    print(f"Total time taken: {time.time() - start_time:.2f} seconds")
    