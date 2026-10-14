import json
import math
import os
from datetime import datetime

def create_sulaymaniyah_grid():
    """
    Creates a large-scale grid system for Sulaymaniyah region.
    Each grid cell is 1km² and named using A1, A2, B1, B2, etc. format.
    Covers the entire greater Sulaymaniyah area including surrounding regions.
    """
    
    # Updated Slemani center coordinates
    center_lat = 35.570478961231416
    center_lon = 45.350180102299475
    
    # Grid parameters - final optimized configuration
    grid_size_km = 1.0  # Each grid cell is 1km²
    grid_width_km = 32.0  # Total grid width: 32km
    grid_height_km = 22.0  # Total grid height: 22km
    grid_cols = 32  # 32 columns
    grid_rows = 22  # 22 rows
    
    # Calculate degrees per km (approximate)
    # 1 degree latitude ≈ 111.32 km
    # 1 degree longitude ≈ 111.32 * cos(latitude) km
    lat_degrees_per_km = 1.0 / 111.32
    lon_degrees_per_km = 1.0 / (111.32 * math.cos(math.radians(center_lat)))
    
    # Calculate the top-left corner of the grid (northwest corner)
    half_height_km = grid_height_km / 2.0
    half_width_km = grid_width_km / 2.0
    start_lat = center_lat + (half_height_km * lat_degrees_per_km)
    start_lon = center_lon - (half_width_km * lon_degrees_per_km)
    
    # Generate grid cells
    grid_data = {
        "city": "Sulaymaniyah_Final",
        "center_coordinates": {
            "latitude": center_lat,
            "longitude": center_lon
        },
        "grid_info": {
            "grid_width_km": grid_width_km,
            "grid_height_km": grid_height_km,
            "cell_size_km": grid_size_km,
            "grid_dimensions": f"{grid_cols}x{grid_rows}",
            "total_cells": grid_cols * grid_rows,
            "created_at": datetime.now().isoformat(),
            "description": "Final 32x22 grid covering Slemani region with 1km² cells"
        },
        "grid_cells": []
    }
    
    print(f"Creating {grid_cols}x{grid_rows} grid for Sulaymaniyah...")
    print(f"Center: ({center_lat}, {center_lon})")
    print(f"Grid covers {grid_width_km}km x {grid_height_km}km")
    print(f"Each cell: {grid_size_km}km x {grid_size_km}km")
    
    for row in range(grid_rows):
        for col in range(grid_cols):
            # Generate grid cell label (A1, A2, ..., V32) for 32x22 grid
            row_letter = chr(65 + row)  # A, B, C, ..., V (22 letters total)
            col_number = col + 1        # 1, 2, 3, ..., 32
            cell_label = f"{row_letter}{col_number}"
            
            # Calculate cell boundaries
            # Top-left corner of the cell
            cell_top_lat = start_lat - (row * grid_size_km * lat_degrees_per_km)
            cell_left_lon = start_lon + (col * grid_size_km * lon_degrees_per_km)
            
            # Other corners of the cell
            cell_bottom_lat = cell_top_lat - (grid_size_km * lat_degrees_per_km)
            cell_right_lon = cell_left_lon + (grid_size_km * lon_degrees_per_km)
            
            # Calculate center of the cell
            cell_center_lat = (cell_top_lat + cell_bottom_lat) / 2
            cell_center_lon = (cell_left_lon + cell_right_lon) / 2
            
            # Calculate distance from city center to cell center
            distance_from_center = haversine_distance(
                center_lat, center_lon, 
                cell_center_lat, cell_center_lon
            )
            
            # Create grid cell data
            grid_cell = {
                "label": cell_label,
                "row": row + 1,
                "column": col + 1,
                "center": {
                    "latitude": round(cell_center_lat, 6),
                    "longitude": round(cell_center_lon, 6)
                },
                "boundaries": {
                    "north": round(cell_top_lat, 6),
                    "south": round(cell_bottom_lat, 6),
                    "east": round(cell_right_lon, 6),
                    "west": round(cell_left_lon, 6)
                },
                "corners": {
                    "northwest": {"lat": round(cell_top_lat, 6), "lon": round(cell_left_lon, 6)},
                    "northeast": {"lat": round(cell_top_lat, 6), "lon": round(cell_right_lon, 6)},
                    "southwest": {"lat": round(cell_bottom_lat, 6), "lon": round(cell_left_lon, 6)},
                    "southeast": {"lat": round(cell_bottom_lat, 6), "lon": round(cell_right_lon, 6)}
                },
                "distance_from_center_km": round(distance_from_center, 2),
                "area_km2": grid_size_km * grid_size_km
            }
            
            grid_data["grid_cells"].append(grid_cell)
    
    return grid_data

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    Returns distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r

def save_grid_to_json(grid_data, filename="sulaymaniyah_final_grid.json"):
    """Save grid data to JSON file"""
    output_path = os.path.join(os.path.dirname(__file__), filename)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(grid_data, f, indent=2, ensure_ascii=False)
    
    print(f"Grid saved to: {output_path}")
    return output_path

def print_grid_summary(grid_data):
    """Print a summary of the generated grid"""
    print("\n" + "="*50)
    print("SULAYMANIYAH GRID SYSTEM SUMMARY")
    print("="*50)
    print(f"City: {grid_data['city']}")
    print(f"Center: ({grid_data['center_coordinates']['latitude']}, {grid_data['center_coordinates']['longitude']})")
    print(f"Total cells: {grid_data['grid_info']['total_cells']}")
    print(f"Grid dimensions: {grid_data['grid_info']['grid_dimensions']}")
    print(f"Each cell area: {grid_data['grid_info']['cell_size_km']}km²")
    print(f"Total coverage: {grid_data['grid_info']['grid_width_km']}km x {grid_data['grid_info']['grid_height_km']}km")
    
    print(f"\nGrid cells range from A1 to V32:")
    print("Rows: A, B, C, ..., V (22 total)")
    print("Columns: 1, 2, 3, ..., 32 (32 total)")
    
    # Show some example cells
    grid_dimensions = grid_data['grid_info']['grid_dimensions'].split('x')
    grid_cols_count = int(grid_dimensions[0])
    grid_rows_count = int(grid_dimensions[1])
    center_row = grid_rows_count // 2  # Center row (around L)
    center_col = grid_cols_count // 2  # Center column (around 12)
    center_index = center_row * grid_cols_count + center_col  # Center cell
    sample_cells = [grid_data['grid_cells'][0], 
                   grid_data['grid_cells'][31],  # A32
                   grid_data['grid_cells'][center_index],  # Center cell (~L16)
                   grid_data['grid_cells'][-1]]  # V32
    
    print(f"\nSample grid cells:")
    for cell in sample_cells:
        print(f"  {cell['label']}: Center ({cell['center']['latitude']}, {cell['center']['longitude']}) - Distance from center: {cell['distance_from_center_km']}km")
    
    print("="*50)

def main():
    """Main function to create and save the grid"""
    print("Creating Sulaymaniyah Grid System...")
    
    # Create the grid
    grid_data = create_sulaymaniyah_grid()
    
    # Print summary
    print_grid_summary(grid_data)
    
    # Save to JSON
    json_path = save_grid_to_json(grid_data)
    
    print(f"\nGrid creation completed successfully!")
    print(f"JSON file saved at: {json_path}")
    print(f"\nYou can now use this grid system for Google Places API searches.")
    print(f"Each grid cell has a center coordinate that you can use as a search point.")

if __name__ == "__main__":
    main()

