# Physics & Hydrodynamics Module — O.C.E.A.N. (SIH26143)

Corrected, tested implementation of Layer 2 (backward Lagrangian hindcast +
Monte Carlo origin cone). This replaces the earlier Gemini-generated draft,
which had the right *shape* but several real bugs — see "What changed" below.

## Quick start

```bash
pip install numpy xarray shapely scipy netCDF4 h5netcdf

# 1. Generate placeholder CMEMS/ERA5-shaped data so you can test today
python make_synthetic_ocean_data.py

# 2. Run the real pipeline against the sample AI-lead output
python hindcast_engine.py
# -> writes output/origin_cone.geojson

# 3. Validate the method against a known synthetic origin (twin experiment)
python twin_experiment.py
# -> prints centroid error (km) and whether the true origin falls inside
#    the 50/75/95% bands -- this is the number to quote to judges
```

Tested end-to-end in this environment: pipeline ran clean, recovered a
synthetic true origin to within ~0.2 km, and the true origin fell inside
all three probability bands. That error is artificially small because the
synthetic field is smooth with no real turbulence — once you swap in real
CMEMS/ERA5 data, expect (and report) a larger, more realistic error. The
point of this run wasn't "the model is 0.2km accurate," it's "the plumbing
— NetCDF loading, RK2 integration, ensemble generation, band export — is
correct end to end."

## Swapping in real data

1. Register for CMEMS (marine.copernicus.eu) and get an ERA5 API key from
   the Copernicus Climate Data Store — do this now, approval isn't always
   instant.
2. Download NetCDF subsets for your demo's exact bounding box and time
   window and save them over `data/cmems_currents.nc` and
   `data/era5_winds.nc`.
3. Run `python inspect_netcdf.py data/cmems_currents.nc` (and the wind
   file) and check the variable names printed against `config.py`'s
   `CURRENT_VARS`/`WIND_VARS` — real downloads sometimes name things
   differently than assumed here. Edit `config.py` if they don't match.
4. Everything else is unchanged — `hindcast_engine.py` doesn't care whether
   the NetCDF file is synthetic or real.

## Demo region

Defaults to Mumbai coastal waters (~72.2–73.2°E, 18.2–19.4°N), matching the
coordinates already in the sample spill polygon you shared. Edit `BOUNDS`
in `make_synthetic_ocean_data.py` and your real CMEMS/ERA5 download extents
if your team targets a different stretch of coast.

## Output contract (what the GIS Architect receives)

`output/origin_cone.geojson` — a FeatureCollection where each feature is
either a probability-band polygon (`probability_band`: 50/75/95,
`timestep_utc`, `hours_before_detection`) at one of several backward
snapshots (every `SNAPSHOT_EVERY_HOURS`, configurable), or a single
`probability_band: "best_estimate"` point marking the anchor for the AIS
time-window query. All geometry is WGS84 (EPSG:4326).

## What changed vs. the earlier draft, and why

| Issue in the earlier draft | Fix here |
|---|---|
| Never actually read the NetCDF files — used hardcoded constant current/wind values regardless of input | `netcdf_loader.py` opens both files with `xarray` and interpolates the real field at each particle's exact lon/lat/time |
| Added fresh random noise to velocity at every integration step — this **is** a random walk (diffusion) run backward, the exact instability we discussed avoiding | Uncertainty now comes only from perturbing each ensemble member's *starting* position and time once; each member's trajectory afterward is fully deterministic |
| `np.linalg_norm` — not a real NumPy function, crashes immediately | Removed; replaced the whole distance calculation with a proper Mahalanobis-distance approach |
| Claimed RK4, delivered a plain Euler step | Implemented real RK2 (midpoint method) |
| Probability bands built from raw Euclidean distance from the mean → near-perfect circles regardless of current direction | Mahalanobis distance accounts for the actual covariance of the particle cloud, so bands come out elongated along the flow, not circular |
| `geopandas` imported, never used | Dropped — one less fragile dependency to install under time pressure |
| Sample spill polygon was a degenerate sliver (0.001° wide, 0.26° tall) | Replaced with a realistic small square footprint for testing |

## If you get PyGNOME working via conda

This standalone engine (xarray + numpy + shapely + scipy) exists partly
because PyGNOME needs a conda install with compiled C++ bindings, which is
a real risk to lose hackathon time to. If a teammate does get
`conda install -c conda-forge pygnome` working cleanly, you can swap
`rk2_backward_step`'s manual integration for PyGNOME's `GridCurrentMover` /
`WindMover` fed by the same reversed fields — the ensemble-of-perturbed-ICs
approach and the "no diffusion mover in backward mode" rule apply exactly
the same way either way. For a 3-day event, this fallback is arguably the
safer default regardless.

## Files

- `config.py` — all tunable parameters and NetCDF variable-name mappings
- `netcdf_loader.py` — opens CMEMS/ERA5 files, interpolates velocity at any point/time
- `hindcast_engine.py` — main pipeline: polygon in → origin cone GeoJSON out
- `twin_experiment.py` — validation: known origin → synthetic detection → recovered origin, scored
- `make_synthetic_ocean_data.py` — generates placeholder NetCDF fixtures
- `inspect_netcdf.py` — sanity-checks a real downloaded NetCDF's variable names
- `data/detected_spill_boundary.geojson` — sample AI-lead output format
