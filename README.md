# 🌊 O.C.E.A.N
### Offshore Culprit Evaluation & Attribution Network

> **Smart India Hackathon 2026** — AI-powered marine oil spill detection, hindcasting & vessel attribution system.

---

## 🚀 What is O.C.E.A.N?

**O.C.E.A.N** is an end-to-end AI + oceanographic physics pipeline that:

1. **Detects** marine oil spills from Sentinel-1/2/3 multi-spectral SAR imagery using a U-Net deep learning segmentation model
2. **Hindcasts** the spill origin via PyGNOME's Lagrangian particle engine running 10,000 reverse Monte Carlo trajectories through CMEMS ocean current fields
3. **Attributes** the spill to the responsible vessel using spatial AIS queries and a 4-factor **Vessel Suspicion Index (VSI)** score

---

## 📂 Project Structure

`
O.C.E.A.N/
├── index.html          # Scroll-animated landing page (frame-by-frame animation)
├── styles.css          # Full design system & component styles
├── script.js           # Canvas animation engine & scroll logic
├── demo.html           # Interactive forensic dashboard demo
├── live-demo/          # Standalone live demo build
│   ├── index.html
│   └── assets/
├── ezgif-frame-*.jpg   # 100 animation frames (satellite/ocean sequence)
└── SIH guide.pdf       # Project documentation
`

---

## 🛰️ Tech Stack

| Layer | Technology |
|---|---|
| Satellite Detection | Sentinel-1 C-SAR · Sentinel-2 MSI · Sentinel-3 OLCI |
| AI Model | U-Net Segmentation · ERA5 Wind Filter |
| Hindcasting | PyGNOME Lagrangian · CMEMS Ocean Currents |
| AIS Attribution | MarineCadastre AIS · PostGIS Spatial Queries |
| Visualization | Vanilla HTML/CSS/JS · Canvas API |

---

## 🌐 Pipeline Overview

`
Satellite SAR Image → U-Net Segmentation → Oil Slick Detected
       ↓
PyGNOME Reverse Advection (10K Monte Carlo particles)
       ↓
Origin Probability Cone → AIS Vessel Intersection
       ↓
VSI Score: Proximity (40%) + Speed Anomaly (25%) + AIS Gap (25%) + Risk Profile (10%)
       ↓
Identified Offender + Evidence Dossier
`

---

## ⚖️ Compliance

Built to enforce **MARPOL 73/78** — the International Convention for the Prevention of Pollution from Ships.

---

## 👤 Author

**Shri K.** — SIH 2026 Team
