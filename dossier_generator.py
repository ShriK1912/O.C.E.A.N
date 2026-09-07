"""Generate O.C.E.A.N. analytical enforcement dossier PDFs from runtime artifacts."""

import json
import os
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as ReportLabImage,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
DARK = colors.HexColor("#12202B")
BLUE = colors.HexColor("#1B587C")
LIGHT_BLUE = colors.HexColor("#EAF2F6")
MID_GREY = colors.HexColor("#66727A")
LINE = colors.HexColor("#C8D2D8")
PALE = colors.HexColor("#F5F7F8")


class NumberedCanvasMixin:
    """Store page canvases so the footer can print Page X of Y."""

    def __init__(self, *args, **kwargs):
        from reportlab.pdfgen import canvas

        self._saved_page_states = []
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(page_count)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        pass


from reportlab.pdfgen.canvas import Canvas


class NumberedCanvas(NumberedCanvasMixin, Canvas):
    def draw_page_number(self, page_count):
        self.saveState()
        self.setStrokeColor(LINE)
        self.setLineWidth(0.4)
        self.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(MID_GREY)
        self.drawString(18 * mm, 9 * mm, f"Case ID: {self.case_id}")
        self.drawRightString(
            A4[0] - 18 * mm,
            9 * mm,
            f"Generated: {self.generated_label}  |  Page {self._pageNumber} of {page_count}",
        )
        self.restoreState()


def _safe_text(value, default="Not available"):
    if value is None or value == "":
        return default
    return str(value)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _artifact_paths(base_dir):
    static_dir = os.path.join(base_dir, "static")
    return {
        "analysis": os.path.join(static_dir, "spill_analysis.json"),
        "spill_boundary": os.path.join(static_dir, "spill_boundary.geojson"),
        "origin": os.path.join(static_dir, "origin_cone.geojson"),
        "original": os.path.join(static_dir, "spill_original.png"),
        "raw_mask": os.path.join(static_dir, "spill_mask_raw.png"),
        "mask": os.path.join(static_dir, "spill_mask.png"),
        "overlay": os.path.join(static_dir, "spill_overlay.png"),
        "hindcast_plot": os.path.join(static_dir, "sanity_check_plot.png"),
        "hindcast_svg": os.path.join(static_dir, "sanity_check_plot.svg"),
    }


def _prepare_image(path, max_width, max_height):
    """Return a ReportLab image sized from the real artifact using Pillow."""
    with Image.open(path) as image:
        image.load()
        width, height = image.size
        ratio = min(max_width / width, max_height / height, 1)
        prepared = ReportLabImage(path, width=width * ratio, height=height * ratio)
        prepared.hAlign = "CENTER"
        return prepared


def _paragraph(text, style):
    return Paragraph(escape(_safe_text(text)).replace("\n", "<br/>") , style)


def _table(rows, widths=None, header=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    for row in range(1 if header else 0, len(rows)):
        if row % 2 == 0:
            commands.append(("BACKGROUND", (0, row), (-1, row), PALE))
    table.setStyle(TableStyle(commands))
    return table


def _flatten_coords(value, output):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            output.append((float(value[0]), float(value[1])))
        else:
            for child in value:
                _flatten_coords(child, output)


def _geometry_summary(geojson):
    points = []
    features = geojson.get("features", []) if isinstance(geojson, dict) else []
    for feature in features:
        geometry = feature.get("geometry") or {}
        _flatten_coords(geometry.get("coordinates", []), points)
    if not points:
        extent = "Not available"
    else:
        lons = [point[0] for point in points]
        lats = [point[1] for point in points]
        extent = f"Lon {min(lons):.5f} to {max(lons):.5f}; Lat {min(lats):.5f} to {max(lats):.5f}"
    return features, points, extent


def _origin_summary(origin):
    features = origin.get("features", []) if isinstance(origin, dict) else []
    best = next((item for item in features if item.get("properties", {}).get("probability_band") == "best_estimate"), None)
    bands = sorted({str(item.get("properties", {}).get("probability_band")) for item in features if item.get("properties", {}).get("probability_band") in (50, 75, 95)})
    coordinates = (best or {}).get("geometry", {}).get("coordinates")
    origin_text = "Not available"
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        origin_text = f"{coordinates[1]:.5f} N, {coordinates[0]:.5f} E"
    properties = origin.get("properties", {}) if isinstance(origin, dict) else {}
    return origin_text, bands, len(properties.get("trajectory", [])), properties.get("detection_time_utc")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("DossierTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=DARK, spaceAfter=8),
        "cover_subtitle": ParagraphStyle("CoverSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=12, leading=17, textColor=BLUE),
        "section": ParagraphStyle("Section", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=DARK, spaceAfter=12),
        "subsection": ParagraphStyle("Subsection", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=BLUE, spaceBefore=8, spaceAfter=6),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=DARK, spaceAfter=7),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=MID_GREY),
        "table": ParagraphStyle("Table", parent=base["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=DARK),
        "table_header": ParagraphStyle("TableHeader", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=colors.white),
        "center": ParagraphStyle("Center", parent=base["BodyText"], alignment=TA_CENTER, fontName="Helvetica", fontSize=9, leading=13, textColor=DARK),
    }


def _cell(value, styles, header=False):
    return Paragraph(_safe_text(value), styles["table_header" if header else "table"])


def _section(title, styles):
    return [Paragraph(title, styles["section"])]


def generate_dossier(base_dir, attribution=None):
    """Read current artifacts and create one uniquely named dossier PDF."""
    generated = datetime.now(timezone.utc).astimezone()
    stamp = generated.strftime("%Y-%m-%d_%H-%M-%S")
    case_id = generated.strftime("OCN-%Y-%m%d-%H%M%S")
    dossier_dir = os.path.join(base_dir, "dossier")
    os.makedirs(dossier_dir, exist_ok=True)
    filename = f"OCEAN_Enforcement_Dossier_{stamp}.pdf"
    output_path = os.path.join(dossier_dir, filename)
    while os.path.exists(output_path):
        generated = generated.replace(microsecond=generated.microsecond + 1)
        stamp = generated.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"OCEAN_Enforcement_Dossier_{stamp}.pdf"
        output_path = os.path.join(dossier_dir, filename)

    paths = _artifact_paths(base_dir)
    analysis = _read_json(paths["analysis"])
    boundary = _read_json(paths["spill_boundary"])
    origin = _read_json(paths["origin"])
    attribution = attribution if isinstance(attribution, dict) else {}
    vessels = attribution.get("vessels") if isinstance(attribution.get("vessels"), list) else []
    lead = attribution.get("lead_suspect") if isinstance(attribution.get("lead_suspect"), dict) else {}
    boundary_features, _, boundary_extent = _geometry_summary(boundary)
    origin_text, bands, trajectory_count, origin_detection_time = _origin_summary(origin)
    from physics_engine import config as physics_config

    detection_time = analysis.get("detection_time_utc") or (
        boundary_features[0].get("properties", {}).get("detection_time_utc")
        if boundary_features else None
    ) or origin_detection_time
    styles = _styles()

    doc = BaseDocTemplate(output_path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=20 * mm, title="O.C.E.A.N. Digital Enforcement Analysis Dossier", author="O.C.E.A.N.", canvasmaker=NumberedCanvas)
    doc.case_id = case_id
    doc.generated_label = generated.strftime("%d-%m-%Y %H:%M:%S %Z")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="dossier", frames=frame, onPage=_draw_header)])

    story = []
    story += [Spacer(1, 25 * mm), Paragraph("O.C.E.A.N.", styles["title"]), Paragraph("Ocean Contamination &amp; Environmental Analysis Network", styles["cover_subtitle"]), Spacer(1, 16 * mm), Paragraph("DIGITAL ENFORCEMENT ANALYSIS DOSSIER", styles["section"])]
    story.append(_table([[_cell("Case ID", styles, True), _cell(case_id, styles, True)], [_cell("Incident", styles), _cell(analysis.get("detection", "Not available"), styles)], [_cell("Status", styles), _cell("ANALYSIS COMPLETE", styles)], [_cell("Generated", styles), _cell(doc.generated_label, styles)], [_cell("Document Reference", styles), _cell(filename, styles)]], widths=[45 * mm, 120 * mm], header=False))
    story += [Spacer(1, 35 * mm), Paragraph("System-generated analytical dossier. Intended to support human review and investigation; it does not by itself constitute a legal determination or proof of liability.", styles["body"]), PageBreak()]

    story += _section("1. EXECUTIVE CASE SUMMARY", styles)
    summary = [[_cell("Field", styles, True), _cell("Value", styles, True)]]
    summary_values = [("Case ID", case_id), ("Detection Time", detection_time), ("Analysis Time", doc.generated_label), ("Classification", analysis.get("detection")), ("Confidence", f"{analysis.get('confidence', 'Not available')}%"), ("Estimated Spill Area", f"{analysis.get('area_km2', 'Not available')} km2"), ("Oil Coverage", f"{analysis.get('oil_percentage', 'Not available')}%"), ("Detected Pixels", analysis.get("oil_pixels")), ("Detection Method", analysis.get("detection_method")), ("Image Source", analysis.get("image_source")), ("Estimated Origin", origin_text), ("Lead Suspect", lead.get("name", "Not available")), ("VSI Score", lead.get("score", "Not available"))]
    summary += [[_cell(key, styles), _cell(value, styles)] for key, value in summary_values]
    story += [_table(summary, widths=[55 * mm, 110 * mm]), Spacer(1, 8), Paragraph("Findings summary: the available artifacts record the classification and detection measurements above. The attribution section reflects the session data supplied by the active demonstration interface and is not independently verified AIS evidence.", styles["body"]), PageBreak()]

    story += _section("2. AI-BASED SPILL DETECTION", styles)
    detection_rows = [[_cell("Measure", styles, True), _cell("Runtime value", styles, True)]] + [[_cell(k, styles), _cell(v, styles)] for k, v in [("Detection Classification", analysis.get("detection")), ("Confidence", f"{analysis.get('confidence', 'Not available')}%"), ("Oil Coverage", f"{analysis.get('oil_percentage', 'Not available')}%"), ("Detected Pixels", analysis.get("oil_pixels")), ("Estimated Area", f"{analysis.get('area_km2', 'Not available')} km2"), ("Detection Method", analysis.get("detection_method"))]]
    story.append(_table(detection_rows, widths=[60 * mm, 105 * mm]))
    for number, label, key in [(1, "Original satellite image", "original"), (2, "Raw segmentation mask", "raw_mask"), (3, "Composite mask preview", "mask"), (4, "Spill overlay", "overlay")]:
        if os.path.isfile(paths[key]):
            story += [Spacer(1, 7), _prepare_image(paths[key], 78 * mm, 43 * mm), Paragraph(f"Figure 2.{number} - {label} ({os.path.basename(paths[key])})", styles["small"])]
    story.append(PageBreak())

    story += _section("3. SPILL GEOMETRY & LOCATION", styles)
    props = boundary_features[0].get("properties", {}) if boundary_features else {}
    geometry_type = boundary_features[0].get("geometry", {}).get("type", "Not available") if boundary_features else "Not available"
    story.append(_table([[ _cell("Field", styles, True), _cell("Value", styles, True)], [_cell("Geometry type", styles), _cell(geometry_type, styles)], [_cell("Feature count", styles), _cell(len(boundary_features), styles)], [_cell("Bounding extent", styles), _cell(boundary_extent, styles)], [_cell("Metadata", styles), _cell(json.dumps(props, ensure_ascii=True), styles)]], widths=[50 * mm, 115 * mm]))
    story += [Spacer(1, 8), Paragraph("Source artifact: static/spill_boundary.geojson. The source GeoJSON is read without modification.", styles["body"]), PageBreak()]

    story += _section("4. HYDRODYNAMIC HINDCAST ANALYSIS", styles)
    story.append(_table([[ _cell("Parameter", styles, True), _cell("Configured/runtime value", styles, True)], [_cell("Backward window", styles), _cell(f"{physics_config.STEPS_BACKWARD_HOURS} hours", styles)], [_cell("Monte Carlo particles", styles), _cell(physics_config.N_ENSEMBLE, styles)], [_cell("Snapshot interval", styles), _cell(f"{physics_config.SNAPSHOT_EVERY_HOURS} hours", styles)], [_cell("Integration method", styles), _cell("RK2 midpoint backward integration", styles)], [_cell("Current dataset", styles), _cell(os.path.relpath(physics_config.CURRENT_NC_PATH, base_dir), styles)], [_cell("Wind dataset", styles), _cell(os.path.relpath(physics_config.WIND_NC_PATH, base_dir), styles)], [_cell("Release-time uncertainty", styles), _cell(f"+/- {physics_config.RELEASE_TIME_JITTER_MINUTES} minutes", styles)]], widths=[60 * mm, 105 * mm]))
    if os.path.isfile(paths["hindcast_plot"]):
        story += [Spacer(1, 10), _prepare_image(paths["hindcast_plot"], 165 * mm, 95 * mm), Paragraph("Figure 4.1 - Hindcast simulation verification (static/sanity_check_plot.png)", styles["small"])]
    elif os.path.isfile(paths["hindcast_svg"]):
        story.append(Paragraph("Hindcast PNG unavailable; SVG artifact exists at static/sanity_check_plot.svg.", styles["body"]))
    story.append(PageBreak())

    story += _section("5. PROBABILISTIC SPILL ORIGIN", styles)
    story.append(_table([[ _cell("Measure", styles, True), _cell("Value", styles, True)], [_cell("Best-estimate origin", styles), _cell(origin_text, styles)], [_cell("Probability bands", styles), _cell(", ".join(bands) if bands else "Not available", styles)], [_cell("Trajectory points", styles), _cell(trajectory_count, styles)], [_cell("Detection time", styles), _cell(origin_detection_time, styles)], [_cell("Source", styles), _cell("static/origin_cone.geojson", styles)]], widths=[55 * mm, 110 * mm]))
    story += [Spacer(1, 10), Paragraph("The origin cone and uncertainty regions are reported from the existing hindcast GeoJSON. No origin coordinates are recalculated by the dossier generator.", styles["body"]), PageBreak()]

    story += _section("6. AIS VESSEL ATTRIBUTION", styles)
    vessel_rows = [[_cell(x, styles, True) for x in ["Rank", "Vessel", "IMO", "Type", "Distance", "Speed behavior", "AIS status", "VSI"]]]
    for index, vessel in enumerate(vessels, 1):
        vessel_rows.append([_cell(vessel.get("rank", index), styles), _cell(vessel.get("name"), styles), _cell(vessel.get("imo"), styles), _cell(vessel.get("type"), styles), _cell(f"{vessel.get('dist', 'N/A')} km", styles), _cell(vessel.get("speed_behavior", "Not available"), styles), _cell(vessel.get("ais_status", "Not available"), styles), _cell(vessel.get("score"), styles)])
    story.append(_table(vessel_rows, widths=[10 * mm, 29 * mm, 18 * mm, 22 * mm, 17 * mm, 27 * mm, 25 * mm, 12 * mm]))
    story += [Spacer(1, 8), Paragraph("Attribution source: current session data supplied by the existing demo interface. This dossier does not represent a live AIS archive query.", styles["body"]), PageBreak()]

    story += _section("7. LEAD SUSPECT ANALYSIS", styles)
    story.append(_table([[ _cell("Field", styles, True), _cell("Current session value", styles, True)], [_cell("Vessel", styles), _cell(lead.get("name"), styles)], [_cell("IMO", styles), _cell(lead.get("imo"), styles)], [_cell("Type", styles), _cell(lead.get("type"), styles)], [_cell("VSI score", styles), _cell(lead.get("score"), styles)]], widths=[55 * mm, 110 * mm]))
    factors = lead.get("factors") if isinstance(lead.get("factors"), list) else []
    factor_rows = [[_cell(x, styles, True) for x in ["Factor", "Observation", "Weight", "Contribution / score"]]]
    for factor in factors:
        factor_rows.append([_cell(factor.get("factor"), styles), _cell(factor.get("observation"), styles), _cell(factor.get("weight"), styles), _cell(factor.get("contribution", "Not available"), styles)])
    if len(factor_rows) > 1:
        story += [Spacer(1, 10), _table(factor_rows, widths=[35 * mm, 75 * mm, 20 * mm, 35 * mm])]
    story.append(PageBreak())

    story += _section("8. EVIDENCE & ANALYTICAL BASIS", styles)
    evidence = [[_cell(x, styles, True) for x in ["Category", "Evidence item", "Source", "Analytical significance"]], [_cell("Satellite / AI Detection", styles), _cell("Classification and segmentation statistics", styles), _cell("spill_analysis.json; mask artifacts", styles), _cell("Supports the recorded spill classification", styles)], [_cell("Spill Geometry", styles), _cell("Detected boundary polygon", styles), _cell("spill_boundary.geojson", styles), _cell("Defines the analyzed slick geometry", styles)], [_cell("Hydrodynamic Hindcast", styles), _cell("Backward ensemble and plot", styles), _cell("origin_cone.geojson; sanity_check_plot.png", styles), _cell("Indicates a modeled origin region", styles)], [_cell("AIS / Vessel Attribution", styles), _cell("Current vessel session records", styles), _cell("demo.html runtime state", styles), _cell("Configured analytical indicators; not live verification", styles)], [_cell("Behavioral Indicators", styles), _cell("Speed and AIS observations", styles), _cell("Current attribution payload", styles), _cell("Supports prioritization for human review", styles)]]
    story.append(_table(evidence, widths=[28 * mm, 42 * mm, 48 * mm, 47 * mm]))
    story.append(PageBreak())

    story += _section("9. ANALYTICAL FINDINGS", styles)
    story += [Paragraph(f"Detected incident: {_safe_text(analysis.get('detection'))}.", styles["body"]), Paragraph(f"Estimated origin: {origin_text}.", styles["body"]), Paragraph(f"Detection confidence: {_safe_text(analysis.get('confidence'))}%.", styles["body"]), Paragraph(f"Lead candidate: {_safe_text(lead.get('name'))}; VSI {_safe_text(lead.get('score'))}.", styles["body"]), Paragraph("The attribution values above are demo / configured attribution data and should be treated as analytical indicators pending qualified human review.", styles["body"]), PageBreak()]

    story += _section("10. TECHNICAL METHODOLOGY", styles)
    story.append(Paragraph("Image Input -> Spill Detection -> Segmentation / Classification -> Spill Boundary Extraction -> Hydrodynamic Hindcast -> Probabilistic Origin Estimation -> AIS Attribution -> Vessel Suspicion Assessment -> Enforcement Dossier", styles["body"]))
    story.append(Paragraph("Implemented components used by this dossier include Flask, Python, the existing AI/classical detection pipeline, GeoJSON artifacts, the existing hindcast engine, Monte Carlo ensemble processing, RK2 integration, ReportLab, and Pillow image preparation.", styles["body"]))
    story.append(PageBreak())

    story += _section("11. DATA PROVENANCE, LIMITATIONS & HUMAN REVIEW", styles)
    story.append(Paragraph("Sources used: static/spill_analysis.json, static/spill_boundary.geojson, static/origin_cone.geojson, available detection image artifacts, available hindcast plot, physics_engine configuration/data references, and the current frontend attribution payload.", styles["body"]))
    story.append(Paragraph("Limitations: model, data, spatial, temporal, and attribution uncertainty may affect results. AIS attribution in the current interface is demo / configured data rather than a verified live archive query. Missing artifacts are omitted or reported as unavailable.", styles["body"]))
    story.append(Paragraph("This dossier is system-generated from the analytical outputs available at the time of report generation. Results may contain model, data, spatial, temporal, or attribution uncertainty. The dossier is intended to support qualified human review and investigation and should not be interpreted as an independent legal finding, final attribution, or proof of liability.", styles["body"]))
    story.append(Spacer(1, 12))
    story.append(_table([[ _cell("Generated by", styles, True), _cell("O.C.E.A.N.", styles, True)], [_cell("Generation timestamp", styles), _cell(doc.generated_label, styles)], [_cell("Case ID", styles), _cell(case_id, styles)]], widths=[55 * mm, 110 * mm]))

    doc.build(story)
    return {"filename": filename, "case_id": case_id, "path": output_path}


def _draw_header(canvas, doc):
    canvas.case_id = doc.case_id
    canvas.generated_label = doc.generated_label
    if canvas.getPageNumber() <= 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, A4[1] - 15 * mm, A4[0] - 18 * mm, A4[1] - 15 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(DARK)
    canvas.drawString(18 * mm, A4[1] - 11 * mm, "O.C.E.A.N.")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MID_GREY)
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 11 * mm, "Digital Enforcement Analysis Dossier")
    canvas.restoreState()
