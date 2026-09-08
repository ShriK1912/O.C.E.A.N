"""
Generates hydrodynamic NetCDF environmental files (CMEMS surface current and ERA5 wind)
covering the spatial and temporal bounds of the analyzed oil spill.

The generated fields use the standard CMEMS/ERA5 variable names (uo, vo, u10, v10)
and dynamically center around the detected spill polygon or provided coordinates.
"""

import os
import json
import argparse
from datetime import datetime, timedelta
import numpy as np
import xarray as xr

DEFAULT_BOUNDS = dict(lon_min=72.0, lon_max=74.0, lat_min=16.5, lat_max=18.5, n_lon=50, n_lat=50)


def extract_spill_centroid_and_time(spill_geojson_path):
    """Read centroid and detection time from spill GeoJSON if available."""
    if not os.path.exists(spill_geojson_path):
        return None, None, None

    try:
        with open(spill_geojson_path, "r") as f:
            data = json.load(f)
        features = data.get("features", [])
        if not features:
            return None, None, None

        props = features[0].get("properties", {})
        dt_str = props.get("detection_time_utc") or props.get("detection_time")
        det_time = None
        if dt_str:
            import re
            clean_str = re.sub(r'(\.\d+)?([+-]\d\d:\d\d|Z)$', '', str(dt_str))
            try:
                det_time = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass

        # Compute centroid from coordinates
        coords = []
        def _get_coords(c):
            if isinstance(c, (list, tuple)):
                if len(c) >= 2 and isinstance(c[0], (int, float)) and isinstance(c[1], (int, float)):
                    coords.append((float(c[0]), float(c[1])))
                else:
                    for sub in c:
                        _get_coords(sub)
        _get_coords(features[0].get("geometry", {}).get("coordinates", []))
        if coords:
            mean_lon = float(np.mean([pt[0] for pt in coords]))
            mean_lat = float(np.mean([pt[1] for pt in coords]))
            return mean_lon, mean_lat, det_time
    except Exception as e:
        print(f"[WARN] Could not parse spill geojson: {e}")
    return None, None, None


def build_grid(center_lon=None, center_lat=None, det_time=None):
    if center_lon is not None and center_lat is not None:
        lon_min = center_lon - 1.2
        lon_max = center_lon + 1.2
        lat_min = center_lat - 1.2
        lat_max = center_lat + 1.2
    else:
        lon_min = DEFAULT_BOUNDS["lon_min"]
        lon_max = DEFAULT_BOUNDS["lon_max"]
        lat_min = DEFAULT_BOUNDS["lat_min"]
        lat_max = DEFAULT_BOUNDS["lat_max"]

    if det_time is None:
        det_time = datetime(2026, 8, 14, 3, 14, 0)

    time_start = np.datetime64((det_time - timedelta(hours=48)).strftime("%Y-%m-%dT%H:00:00"))
    time_end = np.datetime64((det_time + timedelta(hours=12)).strftime("%Y-%m-%dT%H:00:00"))

    lons = np.linspace(lon_min, lon_max, 50)
    lats = np.linspace(lat_min, lat_max, 50)
    times = np.arange(time_start, time_end, np.timedelta64(1, "h"))
    return lons, lats, times


def make_current_file(lons, lats, times, path="data/cmems_currents.nc"):
    """
    Surface current: steady southwestward coastal current (~0.22 m/s)
    plus tidal oscillation and coastal boundary shear.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    nt, nlat, nlon = len(times), len(lats), len(lons)

    hours = (times - times[0]) / np.timedelta64(1, "h")
    # M2 semi-diurnal tidal oscillation
    tidal_u = 0.08 * np.sin(2 * np.pi * hours / 12.42)
    tidal_v = 0.05 * np.cos(2 * np.pi * hours / 12.42)

    lon_grid, lat_grid = np.meshgrid(lons, lats)  # (nlat, nlon)
    base_u = -0.18 + 0.04 * (lat_grid - lats.mean())
    base_v = -0.14 + 0.03 * (lon_grid - lons.mean())

    uo = base_u[None, :, :] + tidal_u[:, None, None]
    vo = base_v[None, :, :] + tidal_v[:, None, None]

    ds = xr.Dataset(
        {
            "uo": (("time", "latitude", "longitude"), uo.astype("float32")),
            "vo": (("time", "latitude", "longitude"), vo.astype("float32")),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )
    ds.to_netcdf(path)
    print(f"[SUCCESS] wrote current field to {path} ({nlon}x{nlat}x{nt})")


def make_wind_file(lons, lats, times, path="data/era5_winds.nc"):
    """
    Surface wind: onshore/alongshore wind forcing with diurnal gust cycle.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    nt = len(times)
    hours = (times - times[0]) / np.timedelta64(1, "h")
    gust = 1.2 * np.sin(2 * np.pi * hours / 24.0)

    u10 = np.full((nt, len(lats), len(lons)), -3.8) + gust[:, None, None]
    v10 = np.full((nt, len(lats), len(lons)), -2.2) + 0.3 * gust[:, None, None]

    ds = xr.Dataset(
        {
            "u10": (("time", "latitude", "longitude"), u10.astype("float32")),
            "v10": (("time", "latitude", "longitude"), v10.astype("float32")),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )
    ds.to_netcdf(path)
    print(f"[SUCCESS] wrote wind field to {path} ({len(lons)}x{len(lats)}x{nt})")


def generate(center_lon=None, center_lat=None, det_time=None, out_dir="data"):
    lons, lats, times = build_grid(center_lon, center_lat, det_time)
    curr_path = os.path.join(out_dir, "cmems_currents.nc")
    wind_path = os.path.join(out_dir, "era5_winds.nc")
    make_current_file(lons, lats, times, curr_path)
    make_wind_file(lons, lats, times, wind_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--spill-geojson", default=None)
    parser.add_argument("--center-lon", type=float, default=None)
    parser.add_argument("--center-lat", type=float, default=None)
    parser.add_argument("--out-dir", default="data")
    args = parser.parse_args()

    c_lon, c_lat, det_time = args.center_lon, args.center_lat, None
    if c_lon is None and args.spill_geojson and os.path.exists(args.spill_geojson):
        c_lon, c_lat, det_time = extract_spill_centroid_and_time(args.spill_geojson)
    elif c_lon is None and os.path.exists("../static/spill_boundary.geojson"):
        c_lon, c_lat, det_time = extract_spill_centroid_and_time("../static/spill_boundary.geojson")
    elif c_lon is None and os.path.exists("data/detected_spill_boundary.geojson"):
        c_lon, c_lat, det_time = extract_spill_centroid_and_time("data/detected_spill_boundary.geojson")

    generate(c_lon, c_lat, det_time, out_dir=args.out_dir)
