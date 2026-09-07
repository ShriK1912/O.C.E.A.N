"""
Simulation hyperparameters and data-schema config for the O.C.E.A.N.
Physics & Hydrodynamics module (Layer 2).

Edit the *_VARS dicts if your actual downloaded CMEMS/ERA5 files use
different variable/dimension names than assumed here -- run
`python inspect_netcdf.py <file.nc>` to check before your first real run.
"""

import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Backward hindcast window ---
STEPS_BACKWARD_HOURS = 36        # how far back to hindcast
DT_SECONDS = 900                 # integration step: 15 minutes
SNAPSHOT_EVERY_HOURS = 3         # write a probability-band snapshot this often

# --- Monte Carlo ensemble ---
N_ENSEMBLE = 500                 # ensemble members (raise to 2000-5000 for final runs)
RELEASE_TIME_JITTER_MINUTES = 30 # +/- uncertainty on the detection timestamp itself

# --- Physical parameters ---
WIND_DRIFT_FACTOR = 0.03         # ~3% windage, standard range is 1-4% for surface oil

# --- Probability bands to export ---
PROBABILITY_BANDS = [50, 75, 95]

# --- CMEMS current file: expected variable names ---
# Copernicus Marine "cur" products typically use these names -- verify with
# inspect_netcdf.py against your real download and adjust if needed.
CURRENT_VARS = {
    "lon": "longitude",
    "lat": "latitude",
    "time": "time",
    "u": "uo",   # eastward sea water velocity (m/s)
    "v": "vo",   # northward sea water velocity (m/s)
}

# --- ERA5 wind file: expected variable names ---
WIND_VARS = {
    "lon": "longitude",
    "lat": "latitude",
    "time": "time",
    "u": "u10",  # 10m eastward wind (m/s)
    "v": "v10",  # 10m northward wind (m/s)
}

# --- File paths ---
CURRENT_NC_PATH = os.path.join(BASE_DIR, "physics_engine", "data", "cmems_currents.nc")
WIND_NC_PATH = os.path.join(BASE_DIR, "physics_engine", "data", "era5_winds.nc")
SPILL_GEOJSON_PATH = os.path.join(BASE_DIR, "static", "spill_boundary.geojson")
OUTPUT_GEOJSON_PATH = os.path.join(BASE_DIR, "static", "origin_cone.geojson")
