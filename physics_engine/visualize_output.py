"""
Visual sanity check: plots the input spill polygon, the probability
bands at the final backward snapshot, and the best-estimate origin point.

Usage: python visualize_output.py [path_to_origin_cone.geojson] [path_to_input_spill.geojson] [output_plot_path]
"""
import os
import sys
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import shape

OUTPUT_GEOJSON = sys.argv[1] if len(sys.argv) > 1 else "output/origin_cone.geojson"
INPUT_GEOJSON = sys.argv[2] if len(sys.argv) > 2 else "data/detected_spill_boundary.geojson"
OUTPUT_PLOT = sys.argv[3] if len(sys.argv) > 3 else "output/sanity_check_plot.png"

BAND_COLORS = {50: "#b30000", 75: "#ff8c00", 95: "#ffd27f"}


def plot_polygon(ax, geom, **kwargs):
    if geom.geom_type == "Polygon":
        polys = [geom]
    elif geom.geom_type == "MultiPolygon":
        polys = list(geom.geoms)
    else:
        return
    label = kwargs.pop("label", None)
    for i, poly in enumerate(polys):
        x, y = poly.exterior.xy
        ax.plot(x, y, label=label if i == 0 else None, **kwargs)
        ax.fill(x, y, alpha=0.25, color=kwargs.get("color", "gray"))


def main():
    if not os.path.exists(OUTPUT_GEOJSON) or not os.path.exists(INPUT_GEOJSON):
        print(f"[WARN] Cannot find input files: {OUTPUT_GEOJSON} or {INPUT_GEOJSON}")
        return

    with open(OUTPUT_GEOJSON) as f:
        cone = json.load(f)
    with open(INPUT_GEOJSON) as f:
        spill = json.load(f)

    fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
    fig.patch.set_facecolor('#0d1520')
    ax.set_facecolor('#070b11')

    # Detected spill polygon
    if spill.get("features"):
        spill_geom = shape(spill["features"][0]["geometry"])
        plot_polygon(ax, spill_geom, color="#00d4ff", linewidth=2, label="Detected Slick (T-0h)")

    # Mean trajectory
    traj = cone.get("properties", {}).get("trajectory", [])
    if traj:
        t_lons = [pt["coordinates"][0] for pt in traj]
        t_lats = [pt["coordinates"][1] for pt in traj]
        ax.plot(t_lons, t_lats, color="#2979ff", linestyle="--", linewidth=1.5, alpha=0.85, label="Mean Backward Advection")

    # Probability bands at the final snapshot
    final_hours_candidates = [
        f["properties"].get("hours_before_detection") for f in cone.get("features", [])
        if isinstance(f.get("properties", {}).get("probability_band"), int)
    ]
    final_hours = max(final_hours_candidates) if final_hours_candidates else 36.0

    for feat in cone.get("features", []):
        props = feat.get("properties", {})
        band = props.get("probability_band")
        if band in (50, 75, 95) and props.get("hours_before_detection") == final_hours:
            geom = shape(feat["geometry"])
            plot_polygon(ax, geom, color=BAND_COLORS.get(band, "gray"), linewidth=1.5,
                         label=f"{band}% Confidence Band (T-{final_hours:g}h)")

    # Best-estimate origin point
    best_pt = None
    for feat in cone.get("features", []):
        if feat.get("properties", {}).get("probability_band") == "best_estimate":
            best_pt = shape(feat["geometry"])
            ax.scatter([best_pt.x], [best_pt.y], color="#fbbf24", edgecolor="#ffffff", marker="*", s=220,
                       zorder=6, label=f"Best-Estimate Origin ({best_pt.y:.3f}°N, {best_pt.x:.3f}°E)")
            break

    ax.set_xlabel("Longitude (°E)", color="#94a3b8", fontsize=10)
    ax.set_ylabel("Latitude (°N)", color="#94a3b8", fontsize=10)
    ax.tick_params(colors="#64748b")
    for spine in ax.spines.values():
        spine.set_color("#1e293b")
    ax.grid(True, linestyle=":", alpha=0.25, color="#00d4ff")

    title = f"O.C.E.A.N. Hydrodynamic Hindcast Engine\nOrigin Cone at {final_hours:g}h Rewind vs. Detected Slick"
    ax.set_title(title, color="#e2e8f0", fontsize=11, fontweight="bold", pad=12)
    legend = ax.legend(loc="best", fontsize=8.5, facecolor="#0f172a", edgecolor="#334155")
    for text in legend.get_texts():
        text.set_color("#cbd5e1")

    ax.set_aspect("equal")
    plt.tight_layout()

    out_path = os.path.abspath(OUTPUT_PLOT)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    plt.savefig(out_path, dpi=120, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"[SUCCESS] Wrote hindcast verification plot to {out_path}")


if __name__ == "__main__":
    main()
