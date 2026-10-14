# Use this scraping code whenever you need to scrape a whole grid of a city.

import json
import pandas as pd
import requests
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('API_KEY')

# Load grid data from JSON file
def load_grid_data(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

# Load categories from Excel file
def load_categories(filename):
    df = pd.read_excel(filename)
    print(df.columns)  # Print the column names for debugging
    categories = []
    for column in ['Kurdish', 'English', 'Arabic']:
        categories.extend(df[column].dropna().tolist())  # Add non-null values from each column
    return categories

# Function to scrape data from Google Maps
def scrape_google_maps(api_key, location, category):
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={location}&radius=1000&type={category}&key={api_key}"
    response = requests.get(url)
    return response.json()  # Return the JSON response

# Main function to perform scraping
def main():
    # Load grid and categories
    grid_data = load_grid_data('Scraping Codes (Google Maps)/erbil_grid.json')
    categories = load_categories('Scraping Codes (Google Maps)/Categories.xlsx')

    results = []

    # Iterate over each grid cell
    for cell in grid_data['grid_cells']:
        location = f"{cell['center']['latitude']},{cell['center']['longitude']}"
        for category in categories:
            print(f"Scraping {category} at {location}...")
            data = scrape_google_maps(api_key, location, category)  # Replace with your actual API key
            results.append({
                'cell_label': cell['label'],
                'category': category,
                'data': data
            })

    # Save results to a JSON file
    with open('Scraping Codes (Google Maps)/erbil_scraping_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("Scraping completed and results saved.")

if __name__ == "__main__":
    main()