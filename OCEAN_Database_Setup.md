# O.C.E.A.N. - AIS Spatial Database Setup Guide

This repository contains the database initialization and spatial pipeline for the **O.C.E.A.N.** (Oil Spill Detection and Attribution) hackathon project. 

It processes raw Automatic Identification System (AIS) vessel tracking data, converts coordinates into indexed PostGIS spatial objects, and enables high-speed geographic attribution (Target Lock) to identify vessels intersecting with simulated oil spill zones.

---

## 🛠️ Prerequisites

Before running the scripts, ensure your local environment has the following installed:
1. **PostgreSQL (v18.6+)** with the **PostGIS (v3.6.2+)** extension enabled.
2. **DBeaver Community Edition** (Database client with built-in Spatial geometry viewer).
3. **PeaZip** (or 7-Zip with Zstandard plugin) to extract `.zst` compression files.

---

## 📦 Step 1: Data Acquisition & Preparation

To replicate the 8.1M+ row dataset testing environment, download a daily snapshot from the US MarineCadastre database.

1. **Download:** Navigate to the [MarineCadastre Vessel Traffic Hub (2026 Data)](https://hub.marinecadastre.gov/pages/vesseltraffic). Download a daily Zstandard archive (e.g., `ais-2026-03-31.csv.zst`).
2. **Extract:** Right-click the `.zst` file and use PeaZip to extract the raw `.csv` file. The file size will expand from ~220 MB to ~835 MB.
3. **Bypass Windows Permissions:** 
   * PostgreSQL runs as a background system service and **cannot** read files from your personal user directories (like `Downloads` or `OneDrive`).
   * **Fix:** Create a public folder at `C:\temp_data\` and move the extracted `ais-2026-03-31.csv` file there.

---

## 🚀 Step 2: Database Initialization Pipeline

Open DBeaver, connect to your `ocean_db` database, and execute the following SQL scripts in order.

### `01_schema.sql` (Schema & Indexes)
* **Purpose:** Drops existing tables to prevent conflicts, constructs the 2026-compliant `ais_raw` staging table, and builds the production `ais_vessels` and `ais_positions` tables.
* **Key Feature:** Automatically builds GIST spatial indexes on geometry columns for sub-second query performance.

### `02_load_data.sql` (Raw Data Ingestion)
* **Purpose:** Uses PostgreSQL's high-speed `COPY` command to bulk-insert the massive CSV file into the staging table.
* **Action Required:** Ensure the file path in the query precisely matches your local setup (e.g., `C:\temp_data\ais-2026-03-31.csv`).
* **Expected Time:** ~45–90 seconds for 8.1 million rows.

### `03_spatialize.sql` (Spatial Transformation)
* **Purpose:** Normalizes the data. It extracts unique ships into the master vessel table and transforms string coordinates into mathematical PostGIS `GEOMETRY(Point, 4326)` objects.
* **Expected Time:** ~1–3 minutes (heavy spatial math processing).

---

## 🎯 Step 3: Attribution Testing

To verify the pipeline works, run the attribution module.

### `04_attribution.sql` (Target Lock)
* **Purpose:** Simulates an oil spill polygon near the Gulf Coast and performs an `ST_Intersects` cross-reference against the 8 million spatial points, filtered by a specific 4-hour time window.
* **Visualization:** Once the query runs in DBeaver, look at the **Results** panel at the bottom. Click the **Spatial tab** on the left edge of the grid to see the intersecting ships rendered dynamically on a live map.

---

## 💡 Troubleshooting

* **Error: `could not open file ... Permission denied`** 
  Move your CSV file to `C:\temp_data\` (See Step 1.3).
* **Error: `function st_intersects() does not exist`** 
  You forgot to enable PostGIS on this specific database. Run `CREATE EXTENSION postgis;` and try again.
* **DBeaver crashes or hangs on mapping:**
  Ensure you have a `LIMIT` or time window filter in your `04_attribution.sql` query. Plotting millions of points on the map at once will consume all available RAM.
