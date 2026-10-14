# This is a good and efficient code for scraping a city without the use of a grid.

import os
import googlemaps
import pandas as pd
import time
from tqdm import tqdm  # For progress bars
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
api_key = os.getenv('API_KEY')
if not api_key:
    raise ValueError("API_KEY not found in .env file. Please add your Google Maps API key to the .env file.")

# Initialize client
gmaps = googlemaps.Client(key=api_key)

# Load search terms from the 'Food' sheet in Categories.xlsx (all columns: English, Kurdish, Arabic), skipping the first row (column names)
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

# Complete list of Iraqi cities with coordinates and their safe radius
cities = {
    "Erbil": {"coordinates": (36.219155, 44.038233), "radius": 16},
    # "Sulaymaniyah": {"coordinates": (35.5571, 45.4356), "radius": 14},  # Using 14km as middle of 13-15km range
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

all_stations = []

for city, city_info in tqdm(cities.items(), desc="Searching cities"):
    coordinates = city_info["coordinates"]
    max_distance_km = city_info["radius"]
    radius_meters = max_distance_km * 1000  # Convert km to meters for the API
    
    for term in tqdm(search_terms, desc=f"Terms in {city}", leave=False):
        try:
            # Text search with current term
            results = gmaps.places(
                query=f"{term}",  # Search for just the term
                location=coordinates,
                radius=radius_meters,
                language='ar' if any(char.isalpha() and ord(char) > 255 for char in term) else 'en'
            )

            # Process results
            for place in results['results']:
                # Calculate distance from city center
                place_lat = place['geometry']['location']['lat']
                place_lng = place['geometry']['location']['lng']
                distance = calculate_distance(coordinates[0], coordinates[1], place_lat, place_lng)
                
                # Only include places within the specified radius
                if distance <= max_distance_km:
                    station_data = {
                        'name': place['name'],
                        'address': place.get('formatted_address'),
                        'city': city,
                        'search_term': term,  # Which term found this
                        'lat': place_lat,
                        'lng': place_lng,
                        'distance_km': round(distance, 2),  # Store distance for reference
                        'types': place.get('types'),
                        'business_status': place.get('business_status'),
                        'rating': place.get('rating'),
                        'user_ratings_total': place.get('user_ratings_total'),
                        'price_level': place.get('price_level'),
                        'place_id': place['place_id'],
                    }

                    # Avoid duplicates by checking place_id
                    if not any(s['place_id'] == station_data['place_id'] for s in all_stations):
                        all_stations.append(station_data)

            # Handle pagination (next page of results)
            while 'next_page_token' in results:
                time.sleep(2)  # Required delay for token activation
                results = gmaps.places(page_token=results['next_page_token'])
                
                # Process additional results
                for place in results['results']:
                    # Calculate distance from city center
                    place_lat = place['geometry']['location']['lat']
                    place_lng = place['geometry']['location']['lng']
                    distance = calculate_distance(coordinates[0], coordinates[1], place_lat, place_lng)
                    
                    # Only include places within the specified radius
                    if distance <= max_distance_km:
                        station_data = {
                            'name': place['name'],
                            'address': place.get('formatted_address'),
                            'city': city,
                            'search_term': term,
                            'lat': place_lat,
                            'lng': place_lng,
                            'distance_km': round(distance, 2),
                            'types': place.get('types'),
                            'business_status': place.get('business_status'),
                            'rating': place.get('rating'),
                            'user_ratings_total': place.get('user_ratings_total'),
                            'price_level': place.get('price_level'),
                            'place_id': place['place_id'],
                        }
                        
                        # Avoid duplicates
                        if not any(s['place_id'] == station_data['place_id'] for s in all_stations):
                            all_stations.append(station_data)

        except Exception as e:
            print(f"\nError searching '{term}' in {city}: {str(e)}")
            continue  # Skip to next term if error occurs

    print(f"✅ Completed {city}: Found {len([s for s in all_stations if s['city'] == city])} places")

# Create DataFrame and remove duplicates
df = pd.DataFrame(all_stations).drop_duplicates('place_id')

# Add governorate information
governorates = {
    "Erbil": "Erbil",
    # "Sulaymaniyah": "Sulaymaniyah",
    # "Duhok": "Duhok",
    # "Basra": "Basra",
    # "Baghdad": "Baghdad",
}
df['governorate'] = df['city'].map(governorates)

print(f"\n✅ Search complete! Found {len(df)} unique places.")

# Save to Excel file
output_path = './Kurdistan_places_Erbil2.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Google Maps', index=False)

print(f"Results saved to {output_path} (Google Maps sheet)")

# Display sample data
print("\nSample data:")
print(df[['name', 'city', 'governorate', 'distance_km']].head())
