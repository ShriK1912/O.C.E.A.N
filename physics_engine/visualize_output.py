"""
Quick visual sanity check: plots the input spill polygon, the probability
bands at the final backward snapshot, and the best-estimate origin point,
so you can eyeball whether the output looks physically reasonable before
sending anything to the AI/CV lead.

Usage: python visualize_output.py [path_to_origin_cone.geojson] [path_to_input_spill.geojson]
Defaults to output/origin_cone.geojson and data/detected_spill_boundary.geojson.
"""
import json
import sys

import matplotlib.pyplot as plt
from shapely.geometry import shape

OUTPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/origin_cone.geojson"
INPUT_PATH = sys.argv[2] if len(sys.argv) > 2 else "data/detected_spill_boundary.geojson"

BAND_COLORS = {50: "#b30000", 75: "#ff8c00", 95: "#ffd27f"}


def plot_polygon(ax, geom, **kwargs):
    """Handles both Polygon and MultiPolygon (real AI/CV segmentation output
    is frequently a MultiPolygon -- a slick fragmented into several patches
    is normal, not an error)."""
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
    with open(OUTPUT_PATH) as f:
        cone = json.load(f)
    with open(INPUT_PATH) as f:
        spill = json.load(f)

    fig, ax = plt.subplots(figsize=(8, 8))

    # input spill polygon (where it was detected)
    spill_geom = shape(spill["features"][0]["geometry"])
    plot_polygon(ax, spill_geom, color="blue", linewidth=2, label="Detected slick (input)")

    # final-snapshot probability bands only, so the plot isn't cluttered
    final_hours = max(
        f["properties"]["hours_before_detection"] for f in cone["features"]
        if isinstance(f["properties"]["probability_band"], int)
    )
    for feat in cone["features"]:
        props = feat["properties"]
        if props["probability_band"] == "best_estimate":
            continue
        if props["hours_before_detection"] != final_hours:
            continue
        band = props["probability_band"]
        geom = shape(feat["geometry"])
        plot_polygon(ax, geom, color=BAND_COLORS.get(band, "gray"), linewidth=1.5,
                     label=f"{band}% band @ {final_hours}h back")

    # best estimate point
    for feat in cone["features"]:
        if feat["properties"]["probability_band"] == "best_estimate":
            pt = shape(feat["geometry"])
            ax.scatter([pt.x], [pt.y], color="black", marker="*", s=200,
                       zorder=5, label="Best-estimate origin")

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Origin cone at {final_hours}h before detection\nvs. detected slick location")
    ax.legend(loc="best", fontsize=8)
    ax.set_aspect("equal")
    plt.tight_layout()
    plt.savefig("output/sanity_check_plot.png", dpi=150)
    print("[SUCCESS] wrote output/sanity_check_plot.png -- open it and eyeball the result")


if __name__ == "__main__":
    main()
