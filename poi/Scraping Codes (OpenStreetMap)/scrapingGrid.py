import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from tqdm import tqdm
import os

# 0️⃣  Increase Overpass timeout (optional but recommended)
ox.settings.overpass_settings = "[out:json][timeout:180];"

# 1️⃣  Config
cities = {
    "Slemani": "Sulaymaniyah, Iraq",
    "Hawler":  "Erbil, Iraq",
}
tags = {
    "amenity": [
        "restaurant", "cafe", "fast_food", "food_court",
        "bar", "pub", "ice_cream", "bakery"
    ]
}
tile_size = 1000  # metres  (≈ 1 km per side)
tiles_per_city = 20  # how many central tiles to query

# 2️⃣  Build square-grid helper
def make_grid(city_gdf, size_m):
    """
    Returns grid (GeoDataFrame WGS-84) of square tiles clipped to city polygon.
    """
    # Re-project to a metric CRS (UTM) so size is in metres
    _, utm_crs = ox.projection.project_geometry(city_gdf.geometry.iloc[0])
    city_utm   = city_gdf.to_crs(utm_crs)

    minx, miny, maxx, maxy = city_utm.total_bounds
    xs = range(int(minx), int(maxx), size_m)
    ys = range(int(miny), int(maxy), size_m)

    tiles = [
        box(x, y, x + size_m, y + size_m)
        for x in xs for y in ys
        if box(x, y, x + size_m, y + size_m).intersects(city_utm.geometry.iloc[0])
    ]

    grid_utm = gpd.GeoDataFrame(geometry=tiles, crs=utm_crs)
    grid_utm = grid_utm[grid_utm.is_valid & ~grid_utm.is_empty]   # ⬅️ filter
    return grid_utm.to_crs("EPSG:4326")


# 3️⃣  Main scraping loop
records = []

# ... (same imports / settings / make_grid as before) ...

tiles_per_city = 20          # keep small for testing
stop_after_first_result = True  # change to False for full loop

for city_label, place_name in cities.items():
    city_poly = ox.geocode_to_gdf(place_name)
    grid, utm_crs, centre = make_grid(city_poly, tile_size)

    # Pick 20 closest tiles
    grid_utm = grid.to_crs(utm_crs)
    central = (
        grid_utm.assign(dist=grid_utm.centroid.distance(centre))
                .sort_values("dist")
                .head(tiles_per_city)
                .to_crs("EPSG:4326")
    )

    for i, tile_geom in enumerate(central.geometry, 1):
        try:
            # 🚨 Check for invalid geometries (important!)
            if tile_geom.is_empty or not tile_geom.is_valid:
                print(f"⚠️  Tile {i}: invalid geometry → skipped")
                continue

            # Now run query
            gdf = ox.features_from_polygon(tile_geom, tags)

        except Exception as e:
            print(f"⚠️  Tile {i}: Overpass error → {e}")
            print(f"    Bounds: {tile_geom.bounds}")
            continue



# 4️⃣  Build DataFrame
df = pd.DataFrame(records)

core_cols = ["name", "Amenity", "City", "Latitude", "Longitude"]
if not df.empty:
    df = df[[*core_cols, *[c for c in df.columns if c not in core_cols]]]

# 5️⃣  Write to / append Excel sheet
out_path = "../Kurdistan_places2.xlsx"
if os.path.exists(out_path):
    with pd.ExcelWriter(out_path, engine="openpyxl",
                        mode="a", if_sheet_exists="replace") as writer:
        df.to_excel(writer, sheet_name="OpenStreetMap", index=False)
else:
    with pd.ExcelWriter(out_path, engine="openpyxl", mode="w") as writer:
        df.to_excel(writer, sheet_name="OpenStreetMap", index=False)

print(f"✅ Finished. Rows saved: {len(df):,}")
