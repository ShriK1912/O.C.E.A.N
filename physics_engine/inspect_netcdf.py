"""
Run this against any real CMEMS/ERA5 file BEFORE plugging it into the
pipeline, to confirm the variable/dimension names match config.py.

Usage: python inspect_netcdf.py data/cmems_currents.nc
"""
import sys
import xarray as xr

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_netcdf.py <path_to.nc>")
        sys.exit(1)
    ds = xr.open_dataset(sys.argv[1])
    print(ds)
    print("\nData variables:", list(ds.data_vars))
    print("Coordinates:", list(ds.coords))
