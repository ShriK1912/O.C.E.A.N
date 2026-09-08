"""
Loads CMEMS current and ERA5 wind NetCDF files and provides high-speed
vectorized interpolation that returns the combined (current + windage)
velocity vector at any batch of (lon, lat, time) points.

Uses scipy.interpolate.RegularGridInterpolator for ultra-fast evaluation
during Monte Carlo backward integration.
"""

import numpy as np
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

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


def _build_grid_interpolator(ds, var_name, lon_name, lat_name, time_name):
    """
    Build a RegularGridInterpolator for a 3D dataset variable.
    Ensures all coordinate axes are strictly ascending (flipping if needed).
    """
    da = ds[var_name]
    dims = list(da.dims)
    data = da.values.copy()

    coords_raw = {
        time_name: da[time_name].values.astype("datetime64[s]").astype(np.float64),
        lat_name: da[lat_name].values.astype(np.float64),
        lon_name: da[lon_name].values.astype(np.float64),
    }

    grid_axes = []
    for axis_idx, dim_name in enumerate(dims):
        coords = coords_raw[dim_name]
        if len(coords) > 1 and coords[1] < coords[0]:
            # Coordinates are descending; flip axis
            coords = np.flip(coords)
            data = np.flip(data, axis=axis_idx)
        grid_axes.append(coords)

    # bounds_error=False, fill_value=None allows nearest extrapolation at boundaries
    interp = RegularGridInterpolator(
        tuple(grid_axes), data, method="linear", bounds_error=False, fill_value=None
    )
    return interp, dims


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

        # Pre-build fast interpolators
        self._curr_u_interp, self._curr_u_dims = _build_grid_interpolator(
            self.ds_curr, self.cv["u"], self.cv["lon"], self.cv["lat"], self.cv["time"]
        )
        self._curr_v_interp, _ = _build_grid_interpolator(
            self.ds_curr, self.cv["v"], self.cv["lon"], self.cv["lat"], self.cv["time"]
        )
        self._wind_u_interp, self._wind_u_dims = _build_grid_interpolator(
            self.ds_wind, self.wv["u"], self.wv["lon"], self.wv["lat"], self.wv["time"]
        )
        self._wind_v_interp, _ = _build_grid_interpolator(
            self.ds_wind, self.wv["v"], self.wv["lon"], self.wv["lat"], self.wv["time"]
        )

    def _eval_field(self, interp, dims, lon_name, lat_name, time_name, lons, lats, times_sec):
        dim_map = {
            time_name: times_sec,
            lat_name: lats,
            lon_name: lons,
        }
        pts = np.column_stack([dim_map[d] for d in dims])
        return interp(pts)

    def total_velocity(self, lons, lats, times):
        """
        lons, lats: 1D arrays of positions (degrees)
        times: 1D array of numpy.datetime64 (same length)
        Returns (u_total, v_total) in m/s -- current plus windage-scaled wind,
        NOT yet sign-flipped for backward integration (caller's job).
        """
        times_sec = times.astype("datetime64[s]").astype(np.float64)

        u_curr = self._eval_field(
            self._curr_u_interp, self._curr_u_dims,
            self.cv["lon"], self.cv["lat"], self.cv["time"],
            lons, lats, times_sec
        )
        v_curr = self._eval_field(
            self._curr_v_interp, self._curr_u_dims,
            self.cv["lon"], self.cv["lat"], self.cv["time"],
            lons, lats, times_sec
        )
        u_wind = self._eval_field(
            self._wind_u_interp, self._wind_u_dims,
            self.wv["lon"], self.wv["lat"], self.wv["time"],
            lons, lats, times_sec
        )
        v_wind = self._eval_field(
            self._wind_v_interp, self._wind_u_dims,
            self.wv["lon"], self.wv["lat"], self.wv["time"],
            lons, lats, times_sec
        )

        u_total = u_curr + config.WIND_DRIFT_FACTOR * u_wind
        v_total = v_curr + config.WIND_DRIFT_FACTOR * v_wind
        return u_total, v_total

    def close(self):
        self.ds_curr.close()
        self.ds_wind.close()
