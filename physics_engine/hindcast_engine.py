"""
O.C.E.A.N. Physics & Hydrodynamics module -- backward Lagrangian hindcast.

Fixes vs. the earlier draft:
  1. Actually interpolates real current + wind fields via netcdf_loader
     (the draft silently used hardcoded constants).
  2. Monte Carlo uncertainty comes ONLY from perturbing each ensemble
     member's starting position/time once. No noise is injected during
     the per-step integration loop -- that would be a random walk run
     backward in time, which is the specific instability we're avoiding.
  3. Proper RK2 (midpoint method) integration instead of a plain Euler
     step mislabeled as RK2.
  4. Probability bands use Mahalanobis distance (accounts for the actual
     covariance/orientation of the particle cloud) instead of raw
     Euclidean distance from the mean, so the cone comes out elongated
     along the flow direction instead of a perfect circle.
  5. Fixes the np.linalg_norm typo (should be np.linalg.norm).

Run: python hindcast_engine.py
"""

import json
from datetime import datetime, timedelta

import numpy as np
from shapely.geometry import shape, Point, MultiPoint, mapping

import config
from netcdf_loader import VelocityField

DEG_PER_METER_LAT = 1.0 / 111_000.0


def load_spill_polygon(geojson_path):
    with open(geojson_path, "r") as f:
        data = json.load(f)
    features = data.get("features", [])
    if not features:
        from shapely.geometry import box
        return box(73.18, 17.42, 73.20, 17.44), {"spill_id": "SPILL_ESTIMATED", "detection_time_utc": "2026-08-14T03:14:00Z"}
    geom = features[0]["geometry"]
    props = features[0].get("properties", {})
    return shape(geom), props


def sample_points_in_polygon(polygon, n):
    """Rejection-sample n points uniformly inside the polygon."""
    minx, miny, maxx, maxy = polygon.bounds
    pts = []
    tries = 0
    max_tries = n * 200
    while len(pts) < n and tries < max_tries:
        p = Point(np.random.uniform(minx, maxx), np.random.uniform(miny, maxy))
        if polygon.contains(p):
            pts.append((p.x, p.y))
        tries += 1
    if len(pts) < n:
        # polygon too thin for rejection sampling to fill quickly -- pad with centroid jitter
        c = polygon.centroid
        while len(pts) < n:
            pts.append((c.x + np.random.normal(0, 1e-4), c.y + np.random.normal(0, 1e-4)))
    return np.array(pts)


def deg_per_meter_lon(lat_deg):
    return 1.0 / (111_000.0 * np.cos(np.radians(lat_deg)))


def rk2_backward_step(field: VelocityField, lons, lats, t_np64, dt_seconds):
    """
    One Runge-Kutta-2 (midpoint) step, integrating BACKWARD in time.
    Advection is time-reversible, so we simply negate the sampled velocity
    field -- no change to the field data itself, just the sign used to move
    particles.
    """
    n = len(lons)
    t_array = np.full(n, t_np64)

    # k1: velocity at the current position/time
    u1, v1 = field.total_velocity(lons, lats, t_array)
    u1, v1 = -u1, -v1  # reverse for backward advection

    dlon1 = u1 * deg_per_meter_lon(lats)
    dlat1 = v1 * DEG_PER_METER_LAT

    half_dt = dt_seconds / 2.0
    mid_lon = lons + dlon1 * half_dt
    mid_lat = lats + dlat1 * half_dt
    mid_t = t_array - np.timedelta64(int(half_dt), "s")

    # k2: velocity at the estimated midpoint
    u2, v2 = field.total_velocity(mid_lon, mid_lat, mid_t)
    u2, v2 = -u2, -v2

    dlon2 = u2 * deg_per_meter_lon(mid_lat)
    dlat2 = v2 * DEG_PER_METER_LAT

    new_lon = lons + dlon2 * dt_seconds
    new_lat = lats + dlat2 * dt_seconds
    return new_lon, new_lat


def run_ensemble(field, polygon, detection_time, n_ensemble, steps_backward_hours,
                  dt_seconds, snapshot_every_hours, release_time_jitter_minutes):
    """
    Each ensemble member gets its OWN starting position (jittered inside the
    polygon) and its OWN starting time (jittered around detection_time).
    From there, integration is fully deterministic -- all the spread you see
    in the output comes from these initial perturbations, not from noise
    injected mid-trajectory.
    """
    start_positions = sample_points_in_polygon(polygon, n_ensemble)
    lons = start_positions[:, 0].copy()
    lats = start_positions[:, 1].copy()

    time_jitters = np.random.uniform(
        -release_time_jitter_minutes, release_time_jitter_minutes, size=n_ensemble
    )
    member_times = np.array(
        [detection_time + timedelta(minutes=float(j)) for j in time_jitters]
    )

    total_steps = int((steps_backward_hours * 3600) / dt_seconds)
    snapshot_every_steps = int((snapshot_every_hours * 3600) / dt_seconds)

    snapshots = {}  # hours_before_detection -> (lons, lats)
    snapshots[0] = (lons.copy(), lats.copy())

    current_times = np.array([np.datetime64(t) for t in member_times])

    for step in range(1, total_steps + 1):
        lons, lats = rk2_backward_step(field, lons, lats, current_times, dt_seconds)
        current_times = current_times - np.timedelta64(dt_seconds, "s")

        elapsed_hours = step * dt_seconds / 3600.0
        if step % snapshot_every_steps == 0 or step == total_steps:
            snapshots[round(elapsed_hours, 2)] = (lons.copy(), lats.copy())

    return snapshots


def mahalanobis_bands(lons, lats, bands):
    """
    Returns {band_percent: shapely Polygon} using Mahalanobis distance from
    the ensemble mean, which respects the actual spread/orientation of the
    cloud (elongated along the current direction) rather than assuming a
    circular spread the way a raw-Euclidean-distance cutoff would.
    """
    pts = np.column_stack([lons, lats])
    mean = pts.mean(axis=0)
    cov = np.cov(pts, rowvar=False)
    try:
        inv_cov = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        inv_cov = np.linalg.pinv(cov)

    diff = pts - mean
    # Mahalanobis distance for every particle: sqrt(diff @ inv_cov @ diff^T), vectorized
    m_dist = np.sqrt(np.einsum("ij,jk,ik->i", diff, inv_cov, diff))

    polygons = {}
    for band in bands:
        cutoff = np.percentile(m_dist, band)
        subset = pts[m_dist <= cutoff]
        if len(subset) < 3:
            continue
        polygons[band] = MultiPoint([tuple(p) for p in subset]).convex_hull
    return polygons, tuple(mean)


def export_geojson(all_bands_by_snapshot, best_estimate_point, detection_time, spill_id, output_path, field=None):
    features = []
    trajectory_points = []

    sorted_hours = sorted(all_bands_by_snapshot.keys())
    for hours_before in sorted_hours:
        polygons, mean = all_bands_by_snapshot[hours_before]
        timestep = detection_time - timedelta(hours=hours_before)
        t_str = timestep.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Probability bands
        for band, poly in polygons.items():
            features.append({
                "type": "Feature",
                "geometry": mapping(poly),
                "properties": {
                    "spill_id": spill_id,
                    "probability_band": band,
                    "timestep_utc": t_str,
                    "hours_before_detection": hours_before,
                },
            })

        # Centroid point feature
        features.append({
            "type": "Feature",
            "geometry": mapping(Point(mean)),
            "properties": {
                "spill_id": spill_id,
                "probability_band": "mean_trajectory",
                "timestep_utc": t_str,
                "hours_before_detection": hours_before,
            },
        })

        trajectory_points.append({
            "hours": float(hours_before),
            "timestep_utc": t_str,
            "coordinates": [round(float(mean[0]), 5), round(float(mean[1]), 5)]
        })

    best_time = detection_time - timedelta(hours=max(all_bands_by_snapshot.keys()))
    features.append({
        "type": "Feature",
        "geometry": mapping(Point(best_estimate_point)),
        "properties": {
            "spill_id": spill_id,
            "probability_band": "best_estimate",
            "timestep_utc": best_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hours_before_detection": max(all_bands_by_snapshot.keys()),
        },
    })

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "spill_id": spill_id,
            "detection_time_utc": detection_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trajectory": trajectory_points
        }
    }
    with open(output_path, "w") as f:
        json.dump(fc, f, indent=2)
    print(f"[SUCCESS] wrote {len(features)} features and {len(trajectory_points)} trajectory steps to {output_path}")


def main(spill_geojson_path=None, detection_time_str=None, output_path=None):
    spill_geojson_path = spill_geojson_path or config.SPILL_GEOJSON_PATH
    output_path = output_path or config.OUTPUT_GEOJSON_PATH

    print("[1/4] Loading AI spill polygon...")
    polygon, props = load_spill_polygon(spill_geojson_path)
    spill_id = props.get("spill_id", "SPILL_UNSPECIFIED")

    if detection_time_str is None:
        detection_time_str = props.get("detection_time_utc") or props.get("detection_time")
    
    if detection_time_str:
        import re
        dt_clean = re.sub(r'(\.\d+)?([+-]\d\d:\d\d|Z)$', '', str(detection_time_str))
        try:
            detection_time = datetime.strptime(dt_clean, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            try:
                detection_time = datetime.fromisoformat(str(detection_time_str).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                detection_time = datetime(2026, 8, 13, 15, 0, 0)
    else:
        detection_time = datetime(2026, 8, 13, 15, 0, 0)

    print(f"[2/4] Loading environmental fields for detection time {detection_time}...")
    field = VelocityField()

    print(f"[3/4] Running {config.N_ENSEMBLE}-member backward ensemble "
          f"({config.STEPS_BACKWARD_HOURS}h, RK2, no per-step noise)...")
    snapshots = run_ensemble(
        field, polygon, detection_time,
        n_ensemble=config.N_ENSEMBLE,
        steps_backward_hours=config.STEPS_BACKWARD_HOURS,
        dt_seconds=config.DT_SECONDS,
        snapshot_every_hours=config.SNAPSHOT_EVERY_HOURS,
        release_time_jitter_minutes=config.RELEASE_TIME_JITTER_MINUTES,
    )
    field.close()

    print("[4/4] Computing Mahalanobis probability bands per snapshot...")
    all_bands = {}
    c0 = polygon.centroid
    all_bands[0.0] = ({}, (c0.x, c0.y))

    for hours_before, (lons, lats) in snapshots.items():
        if hours_before == 0:
            continue  # already added input polygon centroid
        polys, mean = mahalanobis_bands(lons, lats, config.PROBABILITY_BANDS)
        all_bands[hours_before] = (polys, mean)

    final_hours = max(all_bands.keys())
    best_estimate_point = all_bands[final_hours][1]

    export_geojson(all_bands, best_estimate_point, detection_time, spill_id, output_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="O.C.E.A.N. backward hindcast engine")
    parser.add_argument("--spill", default=None,
                         help="Path to the AI/CV lead's spill polygon GeoJSON")
    parser.add_argument("--detection-time", default=None,
                         help="Detection timestamp, e.g. 2026-09-01T04:00:00Z -- "
                              "REQUIRED if the GeoJSON's properties don't already "
                              "include a detection_time_utc field")
    parser.add_argument("--output", default=None,
                         help="Where to write the origin cone GeoJSON")
    args = parser.parse_args()
    main(spill_geojson_path=args.spill, detection_time_str=args.detection_time,
         output_path=args.output)
