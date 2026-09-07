"""
Generates placeholder NetCDF files with the SAME variable/dimension names
real CMEMS current and ERA5 wind downloads use, so you can test the whole
pipeline today, before your real data access is sorted out.

Swap these files for real downloads later -- nothing else needs to change
as long as the variable names match config.py (check with inspect_netcdf.py).

Domain defaults to the Mumbai coastal waters used in the sample spill
polygon (~72.2-73.0 E, 18.4-19.2 N). Adjust BOUNDS below if your team
targets a different stretch of coast for the demo.
"""

import numpy as np
import xarray as xr

BOUNDS = dict(lon_min=72.0, lon_max=74.0, lat_min=16.5, lat_max=18.5, n_lon=50, n_lat=50)
TIME_START = np.datetime64("2026-08-12T00:00:00")
TIME_END = np.datetime64("2026-08-15T00:00:00")
TIME_STEP_HOURS = 1


def build_grid():
    lons = np.linspace(BOUNDS["lon_min"], BOUNDS["lon_max"], BOUNDS["n_lon"])
    lats = np.linspace(BOUNDS["lat_min"], BOUNDS["lat_max"], BOUNDS["n_lat"])
    times = np.arange(TIME_START, TIME_END, np.timedelta64(TIME_STEP_HOURS, "h"))
    return lons, lats, times


def make_current_file(path="data/cmems_currents.nc"):
    """
    Synthetic surface current: a steady southwestward coastal current
    (~0.25 m/s) plus a mild spatial gradient and a slow tidal oscillation,
    so a backward run has something non-trivial to reconstruct.
    """
    lons, lats, times = build_grid()
    nt, nlat, nlon = len(times), len(lats), len(lons)

    hours = (times - times[0]) / np.timedelta64(1, "h")
    tidal = 0.08 * np.sin(2 * np.pi * hours / 12.42)  # M2 tidal-ish period

    lon_grid, lat_grid = np.meshgrid(lons, lats)  # (nlat, nlon)
    base_u = -0.20 + 0.05 * (lat_grid - lats.mean())
    base_v = -0.15 + 0.03 * (lon_grid - lons.mean())

    uo = base_u[None, :, :] + tidal[:, None, None]
    vo = base_v[None, :, :] + 0.5 * tidal[:, None, None]

    ds = xr.Dataset(
        {
            "uo": (("time", "latitude", "longitude"), uo.astype("float32")),
            "vo": (("time", "latitude", "longitude"), vo.astype("float32")),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )
    ds.to_netcdf(path)
    print(f"[SUCCESS] wrote synthetic current field to {path}")


def make_wind_file(path="data/era5_winds.nc"):
    """Synthetic monsoon-ish onshore wind, steadier than the current field."""
    lons, lats, times = build_grid()
    nt = len(times)
    hours = (times - times[0]) / np.timedelta64(1, "h")
    gust = 1.5 * np.sin(2 * np.pi * hours / 24.0)

    u10 = np.full((nt, len(lats), len(lons)), -4.0) + gust[:, None, None]
    v10 = np.full((nt, len(lats), len(lons)), -2.5) + 0.3 * gust[:, None, None]

    ds = xr.Dataset(
        {
            "u10": (("time", "latitude", "longitude"), u10.astype("float32")),
            "v10": (("time", "latitude", "longitude"), v10.astype("float32")),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )
    ds.to_netcdf(path)
    print(f"[SUCCESS] wrote synthetic wind field to {path}")


if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)
    make_current_file()
    make_wind_file()
