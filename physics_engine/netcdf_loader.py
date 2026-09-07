"""
Loads CMEMS current and ERA5 wind NetCDF files and provides a single
interpolation function that returns the combined (current + windage)
velocity vector at any lon/lat/time inside the data's coverage.

This is the piece the earlier draft skipped -- everything downstream
is worthless if this doesn't actually read your real environmental data.
"""

import numpy as np
import xarray as xr

import config


def load_dataset(path):
    """Open a NetCDF file with xarray. Raises a clear error if missing."""
    try:
        return xr.open_dataset(path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Could not find '{path}'. Pre-download your CMEMS/ERA5 subset "
            f"before running -- see make_synthetic_ocean_data.py for a "
            f"placeholder you can test against in the meantime."
        )


def _interp_component(ds, var_name, lon_name, lat_name, time_name, lons, lats, times):
    """
    Interpolate one velocity component at arbitrary (lon, lat, time) points.
    Falls back to nearest-neighbor at the edges instead of returning NaN,
    since a backward trajectory that drifts slightly outside the downloaded
    bounding box should degrade gracefully, not silently zero out.
    """
    da = ds[var_name]
    # xarray vectorized interpolation: pass DataArrays of matching points
    pts = {
        lon_name: xr.DataArray(lons, dims="points"),
        lat_name: xr.DataArray(lats, dims="points"),
        time_name: xr.DataArray(times, dims="points"),
    }
    interpolated = da.interp(**pts, method="linear")
    values = interpolated.values
    if np.isnan(values).any():
        nearest = da.interp(**pts, method="nearest")
        nn_values = nearest.values
        values = np.where(np.isnan(values), nn_values, values)
    return values


class VelocityField:
    """
    Wraps an opened current dataset and an opened wind dataset and exposes
    one method: total surface velocity (current + windage) at a batch of
    (lon, lat, time) points, in m/s.
    """

    def __init__(self, current_path=None, wind_path=None):
        current_path = current_path or config.CURRENT_NC_PATH
        wind_path = wind_path or config.WIND_NC_PATH
        self.ds_curr = load_dataset(current_path)
        self.ds_wind = load_dataset(wind_path)
        self.cv = config.CURRENT_VARS
        self.wv = config.WIND_VARS

    def total_velocity(self, lons, lats, times):
        """
        lons, lats: 1D arrays of positions (degrees)
        times: 1D array of numpy.datetime64 (same length)
        Returns (u_total, v_total) in m/s -- current plus windage-scaled wind,
        NOT yet sign-flipped for backward integration (caller's job).
        """
        u_curr = _interp_component(
            self.ds_curr, self.cv["u"], self.cv["lon"], self.cv["lat"], self.cv["time"],
            lons, lats, times,
        )
        v_curr = _interp_component(
            self.ds_curr, self.cv["v"], self.cv["lon"], self.cv["lat"], self.cv["time"],
            lons, lats, times,
        )
        u_wind = _interp_component(
            self.ds_wind, self.wv["u"], self.wv["lon"], self.wv["lat"], self.wv["time"],
            lons, lats, times,
        )
        v_wind = _interp_component(
            self.ds_wind, self.wv["v"], self.wv["lon"], self.wv["lat"], self.wv["time"],
            lons, lats, times,
        )
        u_total = u_curr + config.WIND_DRIFT_FACTOR * u_wind
        v_total = v_curr + config.WIND_DRIFT_FACTOR * v_wind
        return u_total, v_total

    def close(self):
        self.ds_curr.close()
        self.ds_wind.close()
