import osmnx as ox

# Download all amenities in Sulaymaniyah
place = "Sulaymaniyah, Iraq"
gdf = ox.features_from_place(place, tags={"amenity": True})

# Show all unique amenity values
print(sorted(gdf["amenity"].dropna().unique()))


#amenities list
['animal_breeding', 'animal_shelter', 'arts_centre', 'atm', 'bank', 'bar', 'bbq', 'bench',
'bicycle_parking', 'bicycle_rental', 'bicycle_repair_station', 'brothel', 'bureau_de_change', 
'bus_station', 'cafe', 'car_rental', 'car_wash', 'casino', 'charging_station', 'childcare', 'cinema', 
'clinic', 'college', 'community_centre', 'courthouse', 'culture_center', 'customs', 'dentist', 
'doctors', 'drinking_water', 'driving_school', 'embassy', 'events_venue', 'fast_food', 
'fire_station', 'food_court', 'fountain', 'fuel', 'funeral_hall', 'grave_yard', 'hospital', 
'hunting_stand', 'ice_cream', 'internet_cafe', 'kindergarten', 'language_school', 'library', 
'marketplace', 'monastery', 'motorcycle_parking', 'nightclub', 'nursing_home', 'parking', 
'parking_entrance', 'payment_terminal', 'pharmacy', 'photo_booth', 'place_of_worship', 'police', 
'post_office', 'prison', 'pub', 'public_bath', 'recycling', 'refugee_site', 'restaurant', 'school',
'shelter', 'shower', 'social_centre', 'social_facility', 'stripclub', 'studio', 'taxi', 'telephone',
'theatre', 'toilets', 'townhall', 'training', 'university', 'vehicle_inspection', 'vending_machine',    
'veterinary', 'waste_disposal', 'water_point', 'weighbridge']