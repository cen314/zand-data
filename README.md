# zand-data

Raw source data for the Zand Iraq intelligence platform.

This repository holds the input material used to populate Zand's financial and location intelligence products: ingest pipelines for Iraqi financial market data, and POI datasets for Kurdistan Region.

---

## Contents

```
src/            ← Financial data ingest pipeline (Python)
data/
  samples/      ← Reference PDFs: ISC daily reports, ISX bulletins, CBI statements
poi/            ← KRG Points of Interest raw data (Excel + scraping scripts)
```

---

## Financial Pipeline (`src/`)

Python scripts for ingesting Iraqi financial market data from three sources:

| Source | Description |
|--------|-------------|
| **ISX** | Iraq Stock Exchange — daily trading bulletins |
| **ISC** | Iraqi Securities Commission — daily and annual reports |
| **CBI** | Central Bank of Iraq — monetary policy statements and FX data |

### Sample data (`data/samples/`)

18 reference PDFs covering:
- ISC daily reports (July 2026)
- ISC annual report 2024
- ISX trading bulletins
- CBI statements

These samples are used for pipeline development and testing. Live data is fetched directly from the source institutions.

### Running the pipeline

```bash
cd src
pip install -r requirements.txt
python isx_ingest.py
```

---

## KRG POI Data (`poi/`)

Google Maps and OpenStreetMap POI datasets for Erbil and Kurdistan Region.

| File / Directory | Description |
|-----------------|-------------|
| `Kurdistan_places*.xlsx` | Google Places API results for KRG — multiple collection runs |
| `Kurdistan_places_Erbil*.xlsx` | Erbil-specific collection |
| `OSM_markets_*.xlsx` | OpenStreetMap market data for Erbil |
| `Scraping Codes (Google Maps)/` | Python scripts used to collect Google Places data |
| `Scraping Codes (OpenStreetMap)/` | Python scripts for Overpass API queries |

This data was collected in 2025 as a proof-of-concept for the Zand location intelligence programme. It has since been processed and loaded into the Zand POI database.

---

## Licence

Financial pipeline code: MIT  
Sample PDFs: reproduced for development purposes only — originals © their respective issuers (ISX, ISC, CBI)  
POI Excel data: collected from public sources; Google Places data carries Google ToS restrictions — internal use only, not for redistribution

---

## Ecosystem Position

```
zand-maps        → HOW to build a map (tech stack reference)
zand-location-intelligence → WHAT data exists and where it lives (layer catalogue)
atlas-zand       → THE APP (platform consuming all data)
zand-data (this repo) → RAW source files for building or refreshing the data estate
```
