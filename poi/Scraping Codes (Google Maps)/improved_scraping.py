# This scraping code is very expernsive.

import os
import googlemaps
import pandas as pd
import time
import numpy as np
from tqdm import tqdm
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv
import concurrent.futures

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
api_key = os.getenv('API_KEY')
if not api_key:
    raise ValueError("API_KEY not found in .env file. Please add your Google Maps API key to the .env file.")

# Initialize client
gmaps = googlemaps.Client(key=api_key)

# Load search terms from the 'Food' sheet in Categories.xlsx
search_terms_file = 'Scraping Codes (Google Maps)/Categories.xlsx'
try:
    df_terms = pd.read_excel(search_terms_file, sheet_name='Food', header=None, usecols=[0,1,2])
    # Skip the first row (column names)
    df_terms = df_terms.iloc[1:]
    # Flatten all values, drop blanks, and convert to str
    search_terms = [str(term).strip() for term in df_terms.values.flatten() if pd.notnull(term) and str(term).strip() != '']
    print(f"Loaded {len(search_terms)} search terms from sheet 'Food' in {search_terms_file}")
except Exception as e:
    print(f"Error loading search terms from {search_terms_file} (sheet 'Food'): {e}")

# Cities with coordinates and their safe radius
cities = {
    # "Erbil": {"coordinates": (36.219155, 44.038233), "radius": 16},
    "Sulaymaniyah": {"coordinates": (35.5571, 45.4356), "radius": 14},
    # "Duhok": {"coordinates": (36.8679, 42.9500), "radius": 10},
    # "Basra": {"coordinates": (30.5081, 47.7834), "radius": 18},
    # "Baghdad": {"coordinates": (33.3128, 44.3615), "radius": 25},
}

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula"""
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    # Radius of earth in kilometers is 6371
    km = 6371 * c
    return km

def create_grid_points(center_lat, center_lng, radius_km, search_radius_km):
    """
    Create a grid of points within a circle centered at (center_lat, center_lng) with radius_km.
    Uses optimal non-overlapping grid spacing based on search_radius_km.
    """
    # Calculate optimal grid size to minimize overlap
    # For circles to barely touch: grid_size ≈ search_radius × √2
    grid_size = search_radius_km * 1.414  # √2 ≈ 1.414
    
    # Convert radius from km to degrees (approximately)
    # 1 degree of latitude is approximately 111 km
    radius_lat = radius_km / 111.0
    # 1 degree of longitude varies with latitude
    radius_lng = radius_km / (111.0 * cos(radians(center_lat)))
    
    # Create grid
    lat_min = center_lat - radius_lat
    lat_max = center_lat + radius_lat
    lng_min = center_lng - radius_lng
    lng_max = center_lng + radius_lng
    
    # Convert grid_size from km to degrees
    grid_size_lat = grid_size / 111.0
    grid_size_lng = grid_size / (111.0 * cos(radians(center_lat)))
    
    # Generate grid points
    lat_points = np.arange(lat_min, lat_max, grid_size_lat)
    lng_points = np.arange(lng_min, lng_max, grid_size_lng)
    
    grid_points = []
    for lat in lat_points:
        for lng in lng_points:
            # Check if the point is within the circle
            if calculate_distance(center_lat, center_lng, lat, lng) <= radius_km:
                grid_points.append((lat, lng))
    
    return grid_points

def search_places(location, term, radius=None, rank_by=None, type_param=None, max_pages=2):
    """
    Search for places using the Google Maps Places API.
    
    Args:
        location: Tuple of (latitude, longitude)
        term: Search term
        radius: Search radius in meters (not used if rank_by='distance')
        rank_by: Ranking method ('prominence' or 'distance')
        type_param: Type of place to search for
        max_pages: Maximum number of pages to retrieve (default: 2)
    
    Returns:
        List of places
    """
    places = []
    
    try:
        # Determine language based on the term
        language = 'ar' if any(char.isalpha() and ord(char) > 255 for char in term) else 'en'
        
        # Set up parameters for the search
        params = {
            'location': location,
            'language': language,
            'keyword': term  # Use keyword to catch places that might not be properly categorized
        }
        
        # Add type parameter if provided
        if type_param:
            params['type'] = type_param
        
        # Add either radius or rankby parameter
        if rank_by == 'distance':
            params['rank_by'] = 'distance'
        else:
            params['radius'] = radius
        
        # Perform the search
        results = gmaps.places_nearby(**params)
        
        # Process results
        places.extend(results.get('results', []))
        
        # Handle pagination - correctly using places_nearby for pagination
        page_count = 1
        while 'next_page_token' in results and page_count < max_pages:
            time.sleep(2)  # Required delay for token activation
            results = gmaps.places_nearby(page_token=results['next_page_token'])
            places.extend(results.get('results', []))
            page_count += 1
    
    except Exception as e:
        print(f"Error searching '{term}' at {location}: {str(e)}")
    
    return places

def search_grid_point(grid_point, city, term, city_radius, search_radius=1000, seen_place_ids=None):
    """Search for places around a grid point"""
    results = []
    
    # Initialize seen_place_ids if not provided
    if seen_place_ids is None:
        seen_place_ids = set()
    
    # Types to search for - focus on specific food-related types, drop generic 'establishment'
    types_to_search = ['restaurant', 'cafe', 'bakery', 'meal_takeaway']
    
    # Only use prominence ranking for grid search (more efficient)
    for type_param in types_to_search:
        places = search_places(
            location=grid_point,
            term=term,
            radius=search_radius,
            rank_by='prominence',
            type_param=type_param,
            max_pages=2  # Cap at 2 pages (up to 40 results) to reduce costs
        )
        
        # Process results
        for place in places:
            place_id = place['place_id']
            
            # Skip if we've already seen this place
            if place_id in seen_place_ids:
                continue
                
            # Mark as seen
            seen_place_ids.add(place_id)
            
            place_lat = place['geometry']['location']['lat']
            place_lng = place['geometry']['location']['lng']
            
            # Calculate distance from city center
            city_center = cities[city]["coordinates"]
            distance = calculate_distance(city_center[0], city_center[1], place_lat, place_lng)
            
            # Only include places within the city radius
            if distance <= city_radius:
                station_data = {
                    'name': place['name'],
                    'address': place.get('vicinity', ''),
                    'city': city,
                    'search_term': term,
                    'search_type': type_param if type_param else 'None',
                    'lat': place_lat,
                    'lng': place_lng,
                    'distance_km': round(distance, 2),
                    'types': place.get('types', []),
                    'business_status': place.get('business_status', ''),
                    'rating': place.get('rating', None),
                    'user_ratings_total': place.get('user_ratings_total', None),
                    'price_level': place.get('price_level', None),
                    'place_id': place_id,
                }
                results.append(station_data)
    
    return results, seen_place_ids

def search_city_with_grid(city, city_info, search_terms):
    """Search a city using a grid-based approach"""
    city_results = []
    seen_place_ids = set()  # Track seen place IDs across all searches
    
    # Get city center coordinates and radius
    center = city_info["coordinates"]
    radius_km = city_info["radius"]
    
    # Define search radius in km
    search_radius_km = 1.0  # 1km search radius
    search_radius_meters = int(search_radius_km * 1000)  # Convert to meters for API
    
    # Create optimally spaced grid points
    grid_points = create_grid_points(center[0], center[1], radius_km, search_radius_km)
    print(f"Created {len(grid_points)} optimally spaced grid points for {city}")
    
    # Search each grid point with each search term
    for term in search_terms:
        print(f"Searching term '{term}' in {city}")
        grid_results = []
        
        # Process grid points in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            # Show progress bar for grid points
            for grid_point in tqdm(grid_points, desc=f"Grid points for '{term}'", leave=False):
                future = executor.submit(
                    search_grid_point, grid_point, city, term, radius_km, search_radius_meters, seen_place_ids
                )
                futures.append(future)
            
            # Collect results with progress bar
            for future in tqdm(concurrent.futures.as_completed(futures), 
                              total=len(futures), 
                              desc=f"Processing results for '{term}'", 
                              leave=False):
                results, updated_seen_ids = future.result()
                grid_results.extend(results)
                seen_place_ids.update(updated_seen_ids)  # Update seen place IDs
        
        # Add results to city results
        city_results.extend(grid_results)
        
        # Print progress
        print(f"Found {len(grid_results)} unique places for term '{term}' in {city}")
        print(f"Total unique places found so far: {len(seen_place_ids)}")
    
    return city_results

# Main execution
all_stations = []
all_place_ids = set()  # Track all place IDs for final deduplication check

for city, city_info in tqdm(cities.items(), desc="Searching cities"):
    # Search city with grid-based approach
    city_results = search_city_with_grid(city, city_info, search_terms)
    
    # Add to all stations (early deduplication already happened in search_grid_point)
    all_stations.extend(city_results)
    
    # Track unique place IDs found in this city
    city_place_ids = {place['place_id'] for place in city_results}
    all_place_ids.update(city_place_ids)
    
    print(f"✅ Completed {city}: Found {len(city_results)} places ({len(city_place_ids)} unique)")

# Create DataFrame (no need for drop_duplicates as we already deduplicated)
df = pd.DataFrame(all_stations)

# Final check to ensure no duplicates
print(f"Total places collected: {len(df)}")
print(f"Total unique place_ids: {len(all_place_ids)}")
if len(df) > len(all_place_ids):
    print(f"Removing {len(df) - len(all_place_ids)} duplicate entries...")
    df = df.drop_duplicates('place_id')
    print(f"Final dataset size: {len(df)}")
else:
    print("No duplicates found in final dataset.")

# Add governorate information
governorates = {
    # "Erbil": "Erbil",
    "Sulaymaniyah": "Sulaymaniyah",
    # "Duhok": "Duhok",
    # "Basra": "Basra",
    # "Baghdad": "Baghdad",
}
df['governorate'] = df['city'].map(governorates)

print(f"\n✅ Search complete! Found {len(df)} unique places.")

# Save to Excel file
output_path = './Kurdistan_places_comprehensive.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Google Maps', index=False)

print(f"Results saved to {output_path} (Google Maps sheet)")

# Display sample data
print("\nSample data:")
print(df[['name', 'city', 'governorate', 'search_term', 'search_type', 'distance_km']].head())
