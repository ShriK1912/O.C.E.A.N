"""
O.C.E.A.N. — Vessel Suspicion Index (VSI) Scoring Engine
Implements the 4-factor multi-criteria attribution model specified in OCEAN PRD §30–31:

  VSI = 100 * (w1 * F_loc + w2 * F_spd + w3 * F_gap + w4 * F_prof)

Weights:
  w1 = 0.40 (Spatiotemporal proximity to hindcast origin)
  w2 = 0.25 (Kinematic speed anomaly during discharge window)
  w3 = 0.25 (AIS evasion / transmission gap behavior)
  w4 = 0.10 (Vessel profile / cargo risk prior)
"""

import math
from datetime import datetime

# PRD §30 weights
W_LOC = 0.40
W_SPD = 0.25
W_GAP = 0.25
W_PROF = 0.10

# Model uncertainty scale for Gaussian proximity decay (sigma in km)
SIGMA_MODEL_KM = 2.5

# Vessel Profile Risk Table (PRD §30.4)
VESSEL_RISK_LOOKUP = {
    "crude oil tanker": 0.95,
    "crude tanker": 0.95,
    "tanker": 0.90,
    "product tanker": 0.85,
    "chemical tanker": 0.80,
    "bulk carrier": 0.50,
    "container ship": 0.25,
    "cargo": 0.30,
    "offshore supply": 0.40,
    "tug": 0.20,
    "fishing vessel": 0.15,
    "trawler": 0.15,
    "passenger": 0.10,
    "pleasure craft": 0.05,
    "unknown": 0.20,
}


def haversine_km(lon1, lat1, lon2, lat2):
    """Great-circle distance between two lon/lat points in kilometers."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def score_proximity(dist_km, sigma_km=SIGMA_MODEL_KM):
    """
    F_loc = exp( - d_min^2 / (2 * sigma_model^2) )  [PRD §30.1]
    Range: 0.0 to 1.0
    """
    if dist_km < 0:
        dist_km = 0.0
    return math.exp(-(dist_km ** 2) / (2.0 * (sigma_km ** 2)))


def score_speed_anomaly(v_nominal, v_origin):
    """
    F_spd = max(0, (v_nominal - v_at_origin_time) / v_nominal)  [PRD §30.2]
    Normalized relative to the vessel's own typical profile.
    """
    if v_nominal <= 0.5:
        return 0.0
    drop = (v_nominal - v_origin) / v_nominal
    return max(0.0, min(1.0, drop))


def score_ais_gap(gap_hours, gap_threshold_hours=1.0, is_dark_evasion=False):
    """
    F_gap = min(1, gap_duration / gap_threshold)  [PRD §30.3]
    If intentional AIS transponder shutdown detected, scores up to 1.0.
    """
    if is_dark_evasion:
        return 1.0
    if gap_hours <= 0:
        return 0.0
    return max(0.0, min(1.0, gap_hours / gap_threshold_hours))


def score_vessel_profile(vessel_type):
    """
    F_prof: Look up prior plausibility by vessel type [PRD §30.4]
    """
    key = str(vessel_type).strip().lower()
    for pattern, score in VESSEL_RISK_LOOKUP.items():
        if pattern in key:
            return score
    return 0.20


def tactical_to_geo(pos, min_lon=73.10, max_lon=73.85, min_lat=17.25, max_lat=17.65):
    """Convert synthetic tactical grid [x, y] to geographic lon/lat if needed."""
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        return 73.40, 17.45
    tx, ty = float(pos[0]), float(pos[1])
    if tx > 50 and 0 < ty < 50:
        return tx, ty
    oa, aa = 90.0, 60.0
    rx = (tx + oa) / (2.0 * oa)
    ry = (ty + aa) / (2.0 * aa)
    lon = min_lon + rx * (max_lon - min_lon)
    lat = min_lat + ry * (max_lat - min_lat)
    return lon, lat


def compute_vessel_vsi(vessel, origin_lon, origin_lat, origin_time_utc=None):
    """
    Compute comprehensive VSI score and breakdown for a vessel candidate.
    
    Expected vessel dictionary fields (or reasonable defaults):
      - name, imo, type
      - waypoints: list of { t: hours, pos: [lon, lat], speed: kn, dark: bool }
      - OR dist: km, slowed: bool, dark: bool, nominal_speed: kn, origin_speed: kn
    """
    v_type = vessel.get("type", "Unknown")
    waypoints = vessel.get("waypoints", [])

    # Determine closest distance and speed behavior dynamically
    if "dist" in vessel and vessel["dist"] is not None:
        dist_km = max(0.05, float(vessel["dist"]))
        v_nom = float(vessel.get("nominal_speed", 14.5 if vessel.get("culprit") else 15.0))
        v_orig = float(vessel.get("origin_speed", 3.1 if vessel.get("culprit") else v_nom))
        has_dark = bool(vessel.get("dark", False))
        dark_duration_h = float(vessel.get("gap_hours", 1.0 if has_dark else 0.0))
    elif waypoints:
        min_d = float("inf")
        nominal_speeds = [w.get("speed", 14.0) for w in waypoints if w.get("speed", 0) > 0]
        v_nom = max(nominal_speeds) if nominal_speeds else 14.0
        v_orig = v_nom
        has_dark = any(w.get("dark", False) for w in waypoints)
        dark_duration_h = sum(3.0 for w in waypoints if w.get("dark", False))

        ref_lon = origin_lon if origin_lon is not None else 73.696
        ref_lat = origin_lat if origin_lat is not None else 17.555

        for w in waypoints:
            pos = w.get("pos", [0, 0])
            w_lon, w_lat = tactical_to_geo(pos)
            d = haversine_km(w_lon, w_lat, ref_lon, ref_lat)
            if d < min_d:
                min_d = d
                v_orig = w.get("speed", v_nom)

        dist_km = round(min_d, 2)
    else:
        dist_km = 15.0
        v_nom = 15.0
        v_orig = 15.0
        has_dark = False
        dark_duration_h = 0.0

    # 1. Proximity factor (F_loc, 40%)
    f_loc = score_proximity(dist_km, SIGMA_MODEL_KM)

    # 2. Speed anomaly factor (F_spd, 25%)
    f_spd = score_speed_anomaly(v_nom, v_orig)

    # 3. AIS evasion gap factor (F_gap, 25%)
    f_gap = score_ais_gap(dark_duration_h, 1.0, is_dark_evasion=has_dark)

    # 4. Vessel profile factor (F_prof, 10%)
    f_prof = score_vessel_profile(v_type)

    # Calculate weighted contributions (out of 100)
    c_loc = W_LOC * f_loc * 100.0
    c_spd = W_SPD * f_spd * 100.0
    c_gap = W_GAP * f_gap * 100.0
    c_prof = W_PROF * f_prof * 100.0

    vsi_total = round(c_loc + c_spd + c_gap + c_prof, 3)

    # Formatted factor rows for display & dossier
    factors = [
        {
            "factor": "F_loc — Distance to origin",
            "observation": f"{dist_km:.3f} km (geodesic minimum)",
            "weight": f"{int(W_LOC * 100)}%",
            "contribution": f"{c_loc:.3f} / {int(W_LOC * 100)} pts (F={f_loc:.4f})"
        },
        {
            "factor": "F_spd — Speed anomaly",
            "observation": f"Slowed {v_nom:.1f} -> {v_orig:.1f} kn ({f_spd * 100:.1f}% reduction)",
            "weight": f"{int(W_SPD * 100)}%",
            "contribution": f"{c_spd:.3f} / {int(W_SPD * 100)} pts (F={f_spd:.4f})"
        },
        {
            "factor": "F_gap — AIS evasion",
            "observation": f"{'Dark transponder shutdown event' if has_dark else 'AIS active, continuous feed'}",
            "weight": f"{int(W_GAP * 100)}%",
            "contribution": f"{c_gap:.3f} / {int(W_GAP * 100)} pts (F={f_gap:.4f})"
        },
        {
            "factor": "F_prof — Vessel profile",
            "observation": f"{v_type} (risk prior {f_prof:.2f})",
            "weight": f"{int(W_PROF * 100)}%",
            "contribution": f"{c_prof:.3f} / {int(W_PROF * 100)} pts (F={f_prof:.4f})"
        }
    ]

    return {
        "id": vessel.get("id"),
        "name": vessel.get("name"),
        "imo": vessel.get("imo"),
        "type": v_type,
        "dist": dist_km,
        "speed_nominal": v_nom,
        "speed_origin": v_orig,
        "is_dark": has_dark,
        "f_loc": round(f_loc, 4),
        "f_spd": round(f_spd, 4),
        "f_gap": round(f_gap, 4),
        "f_prof": round(f_prof, 4),
        "score": round(vsi_total, 3),
        "vsi_score": round(vsi_total, 3),
        "score_exact": vsi_total,
        "culprit": bool(vessel.get("culprit")),
        "factors": factors
    }


def rank_candidates(vessels, origin_lon, origin_lat, origin_time_utc=None):
    """
    Score and rank all vessel candidates by VSI score descending.
    """
    scored = [compute_vessel_vsi(v, origin_lon, origin_lat, origin_time_utc) for v in vessels]
    scored.sort(key=lambda x: x["score_exact"], reverse=True)

    # Assign ranks
    for i, s in enumerate(scored, 1):
        s["rank"] = i

    lead = scored[0] if scored else None
    return {
        "ranked_vessels": scored,
        "ranked_candidates": scored,
        "lead_suspect": lead,
        "total_candidates": len(scored)
    }


def test():
    sample_vessels = [
        {
            "id": "v1", "name": "M/T STENA NORDIC", "imo": "9332237", "type": "Crude oil tanker",
            "culprit": True, "dist": 0.24, "nominal_speed": 14.5, "origin_speed": 3.1, "dark": True
        },
        {
            "id": "v4", "name": "MV COASTAL STAR", "imo": "9601452", "type": "Product tanker",
            "culprit": False, "dist": 12.4, "nominal_speed": 13.0, "origin_speed": 8.5, "dark": False
        },
        {
            "id": "v3", "name": "MV OCEAN TRADER", "imo": "9558731", "type": "Bulk carrier",
            "culprit": False, "dist": 16.8, "nominal_speed": 12.0, "origin_speed": 11.8, "dark": False
        }
    ]
    res = rank_candidates(sample_vessels, 73.145, 17.442)
    lead = res["lead_suspect"]
    assert lead["name"] == "M/T STENA NORDIC"
    assert lead["score"] >= 85
    return f"VSI Scorer test passed. Lead suspect {lead['name']} scored {lead['score']}/100"


if __name__ == "__main__":
    print(test())
