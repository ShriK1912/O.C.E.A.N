"""
Twin experiment: the standard way to validate a hindcast model when you have
no real "confession" to check against.

  1. Pick a known true origin point and release time.
  2. Run the SAME velocity field FORWARD from there to generate a synthetic
     detected slick.
  3. Feed that synthetic slick into the real backward pipeline exactly as if
     it came from the AI/CV lead.
  4. Measure: how far is the recovered best-estimate from the true origin?
     Does the true origin actually fall inside the 75%/95% probability bands?

Report these numbers to your team -- this is what backs up the "Validated
Accuracy" claim on the feasibility slide with a real, defensible figure
instead of an assumed one.
"""

import json
from datetime import datetime, timedelta

import numpy as np
from shapely.geometry import Point, MultiPoint, mapping, shape

import config
from netcdf_loader import VelocityField
from hindcast_engine import (
    deg_per_meter_lon, DEG_PER_METER_LAT, run_ensemble, mahalanobis_bands,
    export_geojson,
)

TRUE_ORIGIN_LON = 72.55
TRUE_ORIGIN_LAT = 19.05
TRUE_RELEASE_TIME = datetime(2026, 8, 30, 16, 0, 0)
FORWARD_HOURS = config.STEPS_BACKWARD_HOURS  # symmetric with the backward window


def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def forward_simulate_synthetic_spill(field, lon0, lat0, release_time, hours, dt_seconds,
                                      n_particles=150, buffer_deg=0.01):
    """Small forward-drifting cluster released at the true origin -> becomes
    the synthetic 'detected polygon', with a small buffer to mimic a satellite
    footprint rather than a single point."""
    lons = np.full(n_particles, lon0) + np.random.normal(0, 0.003, n_particles)
    lats = np.full(n_particles, lat0) + np.random.normal(0, 0.003, n_particles)
    t = np.array([np.datetime64(release_time)] * n_particles)

    steps = int((hours * 3600) / dt_seconds)
    for _ in range(steps):
        u, v = field.total_velocity(lons, lats, t)  # NOT reversed -- forward run
        lons = lons + u * deg_per_meter_lon(lats) * dt_seconds
        lats = lats + v * DEG_PER_METER_LAT * dt_seconds
        t = t + np.timedelta64(dt_seconds, "s")

    cloud = MultiPoint([(x, y) for x, y in zip(lons, lats)])
    synthetic_polygon = cloud.convex_hull.buffer(buffer_deg)
    detection_time = release_time + timedelta(hours=hours)
    return synthetic_polygon, detection_time


def main():
    field_fwd = VelocityField()
    print(f"[1/3] Forward-simulating synthetic spill from true origin "
          f"({TRUE_ORIGIN_LON}, {TRUE_ORIGIN_LAT}) over {FORWARD_HOURS}h...")
    synthetic_polygon, detection_time = forward_simulate_synthetic_spill(
        field_fwd, TRUE_ORIGIN_LON, TRUE_ORIGIN_LAT, TRUE_RELEASE_TIME,
        FORWARD_HOURS, config.DT_SECONDS,
    )
    field_fwd.close()

    synthetic_geojson_path = "data/twin_synthetic_spill.geojson"
    fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": mapping(synthetic_polygon),
            "properties": {
                "spill_id": "TWIN_TEST_001",
                "detection_time_utc": detection_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        }],
    }
    with open(synthetic_geojson_path, "w") as f:
        json.dump(fc, f, indent=2)
    print(f"    synthetic detection polygon written to {synthetic_geojson_path}")

    print("[2/3] Running the real backward pipeline against the synthetic detection...")
    field_bwd = VelocityField()
    snapshots = run_ensemble(
        field_bwd, synthetic_polygon, detection_time,
        n_ensemble=config.N_ENSEMBLE,
        steps_backward_hours=config.STEPS_BACKWARD_HOURS,
        dt_seconds=config.DT_SECONDS,
        snapshot_every_hours=config.SNAPSHOT_EVERY_HOURS,
        release_time_jitter_minutes=config.RELEASE_TIME_JITTER_MINUTES,
    )
    field_bwd.close()

    all_bands = {}
    for hours_before, (lons, lats) in snapshots.items():
        if hours_before == 0:
            continue
        polys, mean = mahalanobis_bands(lons, lats, config.PROBABILITY_BANDS)
        all_bands[hours_before] = (polys, mean)

    final_hours = max(all_bands.keys())
    polys_final, best_estimate = all_bands[final_hours]

    export_geojson(all_bands, best_estimate, detection_time, "TWIN_TEST_001",
                    "output/twin_origin_cone.geojson")

    print("[3/3] Scoring against the known true origin...")
    error_km = haversine_km(TRUE_ORIGIN_LON, TRUE_ORIGIN_LAT, best_estimate[0], best_estimate[1])
    true_point = Point(TRUE_ORIGIN_LON, TRUE_ORIGIN_LAT)

    print(f"\n=== TWIN EXPERIMENT RESULT ===")
    print(f"True origin:        ({TRUE_ORIGIN_LON}, {TRUE_ORIGIN_LAT})")
    print(f"Best-estimate:      ({best_estimate[0]:.4f}, {best_estimate[1]:.4f})")
    print(f"Centroid error:     {error_km:.2f} km")
    for band in config.PROBABILITY_BANDS:
        if band in polys_final:
            inside = polys_final[band].contains(true_point)
            print(f"True origin inside {band}% band: {inside}")


if __name__ == "__main__":
    main()
