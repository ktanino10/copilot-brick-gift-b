"""Defined 2D screening measurements on sampled, actual FreeCAD face boundaries."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from shapely import affinity, contains_xy, maximum_inscribed_circle
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

PROPOSAL = Path(__file__).resolve().parents[1]
ROOT = PROPOSAL.parents[1]
WORK = ROOT / ".work/plate-v2"
sys.path.insert(0, str(ROOT / "source/scripts"))
from legible_metrics import require, pieces, closed_ring, contour_polygon, ink_shape, central_chords, aperture_pocket, aperture_width, material_core_split, plan_rows






















def plan_lettering(config):
    source = json.loads((WORK / "raw-outlines.json").read_text())
    rows = plan_rows(source["candidate_raw"], config["screening_targets_mm"], 134.0)
    plan = {
        "revision": config["revision"], "lines": config["lines"],
        "method": "Preserve exterior font contours except the e mouth; widen only inner counter loops. Add spacing only where original kerning is below the target; never compress the text horizontally.",
        "raw_outlines_sha256": hashlib.sha256((WORK / "raw-outlines.json").read_bytes()).hexdigest(),
        "rows": rows,
    }
    (PROPOSAL / "letter-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"planned_row_widths_mm": [row["width_mm"] for row in rows]}))


def measure_row(row):
    result = {key: value for key, value in row.items() if key != "glyphs"}
    glyph_metrics = []
    for glyph in row["glyphs"]:
        ink = ink_shape(glyph)
        counters = []
        for face in glyph["faces"]:
            for points in face["holes"]:
                hole = contour_polygon(points)
                horizontal, vertical = central_chords(hole)
                counters.append({
                    "maximum_inscribed_diameter_mm": 2 * maximum_inscribed_circle(hole, tolerance=.001).length,
                    "minimum_horizontal_chord_in_central_half_mm": horizontal,
                    "minimum_vertical_chord_in_central_half_mm": vertical,
                    "area_mm2": hole.area,
                })
        item = {
            "index": glyph["index"], "character": glyph["character"],
            "components": len(pieces(ink)), "closed_counters": counters,
            "material_core_split_diameter_mm": material_core_split(ink),
        }
        if glyph["character"] in "ce":
            item["right_aperture_effective_width_mm"] = aperture_width(ink)
        if glyph["character"] in ".i/":
            item["component_inscribed_diameters_mm"] = [
                2 * maximum_inscribed_circle(component, tolerance=.001).length for component in pieces(ink)
            ]
        glyph_metrics.append(item)
    result["glyph_metrics"] = glyph_metrics
    result["minimum_adjacent_glyph_clearance_mm"] = min(
        item["clearance_mm"] for item in row["adjacent_glyphs"]
    )
    result["front_face_side_margin_mm"] = min(row["bounds_mm"][0][0] - 2, 140 - row["bounds_mm"][1][0])
    return result


def measure_final(config):
    outlines = json.loads((WORK / "final-outlines.json").read_text())
    report = {
        "revision": config["revision"], "status": config["status"],
        "definitions": {
            "source": "Reopened native cap faces matched to per-glyph FreeCAD faces; boundaries sampled with0.002mm deflection. Closed-wire endpoints differing by less than1e-8mm are identified as the same endpoint; no polygon healing or CAD geometry repair is performed.",
            "closed_counter": "Largest inscribed disk plus 101 horizontal and 101 vertical chords spanning the middle 25%-75% of the counter bounding box. The shortest middle-band chord is a defined effective throat, not the zero-width tip.",
            "open_c_e": "Largest convex-hull pocket seed, then the widest negative-space escape to the right with a 0.01mm distance-transform grid. Diameter resolution approximately +/-0.03mm; not a universal nozzle rule.",
            "glyph_spacing": "Exact OpenCASCADE minimum distance between adjacent visible glyph compounds; spaces and punctuation retained.",
            "spacing_plan_tolerance": "The1.05mm planning target uses boundaries with0.002mm deflection per glyph. Exact BRep gaps are reported without substituting the target; the check allows0.004mm planning error and separately requires at least1mm.",
            "straight_stroke": "Existing parallel straight-edge material gauges; not a guarantee for all curves or terminals.",
            "material_core": "First 0.005mm erosion-radius sample splitting one ink component into two cores of at least 0.05mm2. Report diameter 2r; this screens sustained material necks, not taper tips. Null means no such split found up to2.4mm, not a minimum-width guarantee.",
            "dot_slash": "Inscribed diameters of actual disconnected i/dot/slash components, without claiming constant width at mathematical endpoints.",
            "scope": "Digital candidate screening only. Actual nozzle0.2mm is known; no verified slicer profile or physical pass is implied.",
        },
        "current": [measure_row(row) for row in outlines["current"]],
        "candidate": [measure_row(row) for row in outlines["candidate"]],
    }
    current_gap = report["current"][0]["bounds_mm"][0][1] - report["current"][1]["bounds_mm"][1][1]
    candidate_gap = report["candidate"][0]["bounds_mm"][0][1] - report["candidate"][1]["bounds_mm"][1][1]
    report["row_gap_mm"] = {"current": current_gap, "candidate": candidate_gap}
    report["relief_mm"] = {"current": .8, "candidate": 1.2}
    for row in report["candidate"]:
        require(row["minimum_adjacent_glyph_clearance_mm"] >= max(
            1.0, config["screening_targets_mm"]["adjacent_glyph_clearance"] - .004
        ),
                "Native lettering does not meet the planned inter-glyph clearance.")
        require(row["minimum_reliable_straight_stroke_mm"] >= 1.0, "A measured straight material stroke is under1mm.")
        for glyph in row["glyph_metrics"]:
            for counter in glyph["closed_counters"]:
                require(min(counter["minimum_horizontal_chord_in_central_half_mm"],
                            counter["minimum_vertical_chord_in_central_half_mm"]) >= 1.015,
                        "A native counter is smaller than the planned effective1.02mm throat.")
            if glyph["character"] in "ce":
                require(glyph["right_aperture_effective_width_mm"] >= .99,
                        "An effective c/e opening remains below approximately1mm.")
    (PROPOSAL / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        version: [{
            "height_mm": row["ink_height_mm"], "width_mm": row["width_mm"],
            "min_spacing_mm": row["minimum_adjacent_glyph_clearance_mm"],
            "straight_stroke_mm": row["minimum_reliable_straight_stroke_mm"],
        } for row in report[version]] for version in ("current", "candidate")
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("plan", "final"))
    args = parser.parse_args()
    config = json.loads((PROPOSAL / "config.json").read_text())
    if args.stage == "plan":
        plan_lettering(config)
    else:
        measure_final(config)
