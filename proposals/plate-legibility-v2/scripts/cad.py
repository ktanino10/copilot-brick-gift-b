"""Candidate-only FreeCAD geometry; production inputs are read-only."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

import FreeCAD as App
import MeshPart
import Part

PROPOSAL = Path(__file__).resolve().parents[1]
ROOT = PROPOSAL.parents[1]
WORK = ROOT / ".work/plate-v2"
sys.path.insert(0, str(ROOT / "source/scripts"))
from freecad_geometry import bounds_list
from letter_metrics import straight_strokes
from legible_lettering import require, face_data, raw_row, edited_glyph




def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")






def rows_from_config(config, current=False):
    reference = ROOT / "revisions/4.0-B-personal-kit.2/parameters.json"
    parameters = json.loads(reference.read_text())
    rows = []
    for number, text in enumerate(config["lines"]):
        if current:
            font = ROOT / "source" / parameters["message"]["font"]
            size = parameters["variants"][0]["text_sizes"][number]
            height = parameters["variants"][0]["text_heights"][number]
            bottom = parameters["message"]["line_bottoms"][number]
            uniform = False
        else:
            row = config["rows"][number]
            font = (ROOT if row["font_root"] == "repository" else PROPOSAL) / row["font"]
            size, height, bottom = row["initial_size"], row["ink_height_mm"], row["bottom_mm"]
            uniform = row["scale_mode"] == "uniform"
        require(font.is_file(), f"Required licensed font is missing: {font.name}")
        shapes, sx, sy = raw_row(text, font, size, height, uniform)
        rows.append({
            "number": number + 1, "text": text, "font": font.name,
            "font_sha256": hashlib.sha256(font.read_bytes()).hexdigest(),
            "x_scale": sx, "y_scale": sy, "bottom_mm": bottom, "shapes": shapes,
        })
    return rows


def row_data(row):
    shape = Part.makeCompound([item[2] for item in row["shapes"]])
    bounds = bounds_list(shape)
    glyphs = [{"index": i, "character": char, "faces": face_data(geom)}
              for i, char, geom in row["shapes"]]
    gauges = straight_strokes(shape.Faces)
    gaps = [{
        "indices": [left[0], right[0]], "pair": left[1] + right[1],
        "clearance_mm": left[2].distToShape(right[2])[0],
    } for left, right in zip(row["shapes"], row["shapes"][1:])]
    return {
        key: value for key, value in row.items() if key != "shapes"
    } | {
        "bounds_mm": bounds, "width_mm": bounds[1][0] - bounds[0][0],
        "ink_height_mm": bounds[1][1] - bounds[0][1],
        "glyphs": glyphs, "adjacent_glyphs": gaps,
        "minimum_reliable_straight_stroke_mm": min(item["width_mm"] for item in gauges),
    }


def export_outlines(config):
    write_json(WORK / "raw-outlines.json", {
        "current": [row_data(row) for row in rows_from_config(config, current=True)],
        "candidate_raw": [row_data(row) for row in rows_from_config(config)],
    })
    print("Exported actual CAD glyph contours for measurement; no print files were changed.")




def finish_rows(config, plan, current=False):
    rows = rows_from_config(config, current=current)
    for row in rows:
        if not current:
            instructions = {item["index"]: item for item in plan["rows"][row["number"] - 1]["glyphs"]}
            revised = []
            for index, char, shape in row["shapes"]:
                operation = instructions[index]
                require(operation["character"] == char, "Plan does not match exact glyph identity.")
                original_faces = len(shape.Faces)
                original_holes = sum(len(face.Wires) - 1 for face in shape.Faces)
                shape = edited_glyph(shape, operation)
                require(len(shape.Faces) == original_faces
                        and sum(len(face.Wires) - 1 for face in shape.Faces) == original_holes,
                        f"Glyph topology changed: row{row['number']} index{index} {char}")
                shape.translate(App.Vector(operation["extra_x_mm"], 0, 0))
                revised.append((index, char, shape))
            row["shapes"] = revised
        bounds = Part.makeCompound([shape for _, _, shape in row["shapes"]]).BoundBox
        margin = (142 - bounds.XLength) / 2 - 2
        require(current or margin >= config["screening_targets_mm"]["front_face_side_margin"] - 1e-5,
                f"Row{row['number']} does not fit the unchanged tapered face.")
        offset = App.Vector((142 - bounds.XLength) / 2 - bounds.XMin, row["bottom_mm"], 0)
        for _, _, shape in row["shapes"]:
            shape.translate(offset)
    return rows


def raised_rows(rows, height):
    solids = []
    for row in rows:
        for _, _, shape in row["shapes"]:
            for face in shape.Faces:
                raised = face.extrude(App.Vector(0, 0, height))
                raised.translate(App.Vector(0, 0, 2.4))
                solids.append(raised)
    return solids


def save_native(shape, path, part_id, lines, config):
    document = App.newDocument("NameplateCandidate")
    obj = document.addObject("Part::Feature", "Candidate")
    obj.Shape = shape
    for key, value in {
        "PartID": part_id, "DisplayLines": json.dumps(lines),
        "Status": config["status"], "Revision": config["revision"],
        "Units": "mm", "PrintOrientation": "flat rear on bed, relief up",
        "ManualColorChange": "After black support at 2.4 mm, before first white path; no Pause encoded",
    }.items():
        obj.addProperty("App::PropertyString", key)
        setattr(obj, key, value)
    obj.addProperty("App::PropertyFloat", "BlackSupportHeight")
    obj.BlackSupportHeight = 2.4
    obj.addProperty("App::PropertyFloat", "WhiteReliefHeight")
    obj.WhiteReliefHeight = config["relief_mm"]
    document.recompute()
    document.saveAs(str(path))
    App.closeDocument(document.Name)
    reopened = App.openDocument(str(path))
    reread = reopened.getObject("Candidate")
    require(json.loads(reread.DisplayLines) == lines and reread.PartID == part_id,
            "Native reopen lost exact text or part identity.")
    require(reread.Shape.isValid() and len(reread.Shape.Solids) == 1,
            "Native reopen produced an invalid solid.")
    require(shape.cut(reread.Shape).Volume + reread.Shape.cut(shape).Volume < 1e-6,
            "Native reopen changed the candidate.")
    reread_shape = reread.Shape.copy()
    App.closeDocument(reopened.Name)
    return reread_shape


def export_stl(shape, path):
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=.0125,
                                  AngularDeflection=math.radians(8), Relative=False)
    with path.open("wb") as stream:
        stream.write(b"Candidate only; millimeters; not sliced".ljust(80, b"\0"))
        stream.write(struct.pack("<I", mesh.CountFacets))
        for facet in mesh.Facets:
            values = list(facet.Normal) + [value for point in facet.Points for value in point]
            stream.write(struct.pack("<12fH", *values, 0))
    return mesh.CountFacets


def cap_faces(shape, z):
    return [face for face in shape.Faces
            if face.BoundBox.ZLength < 1e-6 and abs(face.BoundBox.ZMin - z) < 1e-6]


def section_data(shape, x):
    wires = shape.slice(App.Vector(1, 0, 0), x)
    require(bool(wires), "The requested actual native section is empty.")
    return [[[point.y, point.z] for point in wire.discretize(Deflection=.002)] for wire in wires]


def build(config):
    plan = json.loads((PROPOSAL / "letter-plan.json").read_text())
    require(plan["lines"] == config["lines"], "Candidate plan has different display lines.")
    rows = finish_rows(config, plan)
    old_rows = finish_rows(config, plan, current=True)
    old_document = App.openDocument(str(ROOT / "revisions/4.0-B-personal-kit.2/nameplate/plate.FCStd"))
    original = old_document.getObject("ReplacementPlate").Shape.copy()
    App.closeDocument(old_document.Name)
    clip = Part.makeBox(160, 60, 2.4, App.Vector(-5, -5, 0))
    carrier = original.common(clip).removeSplitter()
    require(carrier.isValid() and len(carrier.Solids) == 1, "Cannot reuse the original black carrier.")
    original_text = Part.makeCompound(raised_rows(old_rows, .8))
    rebuilt_old = carrier.multiFuse(original_text.Solids).removeSplitter()
    original_difference = original.cut(rebuilt_old).Volume + rebuilt_old.cut(original).Volume
    require(original_difference < 1e-5, "Reference glyph reconstruction differs from the current native.")
    shape = carrier.multiFuse(raised_rows(rows, config["relief_mm"])).removeSplitter()
    require(shape.isValid() and len(shape.Solids) == 1 and shape.Volume > 0, "Invalid candidate solid.")
    candidate_carrier = shape.common(clip).removeSplitter()
    carrier_difference = carrier.cut(candidate_carrier).Volume + candidate_carrier.cut(carrier).Volume
    require(carrier_difference < 1e-6, "The black carrier was changed.")
    output = PROPOSAL / "candidate"
    output.mkdir(exist_ok=True)
    carrier.exportBrep(str(output / "unchanged-carrier.brep"))
    reread = save_native(shape, output / "plate.FCStd", config["part"], config["lines"], config)
    reread.exportStep(str(output / "plate.step"))
    step = Part.read(str(output / "plate.step"))
    require(step.isValid() and len(step.Solids) == 1 and abs(step.Volume - reread.Volume) < 1e-5,
            "Exported STEP differs from reopened native.")
    triangle_count = export_stl(reread, output / "plate.stl")
    current_top = Part.makeCompound(cap_faces(original, 3.2))
    candidate_top = Part.makeCompound(cap_faces(reread, 3.6))
    planned_top = Part.makeCompound([s for row in rows for _, _, s in row["shapes"]])
    planned_top.translate(App.Vector(0, 0, 3.6))
    require(candidate_top.cut(planned_top).Area + planned_top.cut(candidate_top).Area < 1e-5,
            "Native top contours differ from measured glyphs.")
    actual_preview = {
        "current_top": face_data(current_top), "candidate_top": face_data(candidate_top),
        "current_section_x71": section_data(original, 71),
        "candidate_section_x71": section_data(reread, 71),
    }
    write_json(WORK / "actual-native-preview.json", actual_preview)
    write_json(WORK / "final-outlines.json", {
        "current": [row_data(row) for row in old_rows],
        "candidate": [row_data(row) for row in rows],
    })
    coupon_rows = []
    coupon_widths = []
    ranges = config["coupon"]["source_character_ranges_inclusive"]
    for row, (first, last) in zip(rows, ranges):
        chosen = [(i, char, geom.copy()) for i, char, geom in row["shapes"] if first <= i <= last]
        bounds = Part.makeCompound([s for _, _, s in chosen]).BoundBox
        coupon_widths.append(bounds.XLength)
        coupon_rows.append({**row, "text": row["text"][first:last + 1], "shapes": chosen})
    all_bounds = Part.makeCompound([s for row in coupon_rows for _, _, s in row["shapes"]]).BoundBox
    margin = config["coupon"]["margin_mm"]
    width = math.ceil((max(coupon_widths) + 2 * margin) * 10) / 10
    height = math.ceil((all_bounds.YLength + 2 * margin) * 10) / 10
    for row in coupon_rows:
        bounds = Part.makeCompound([s for _, _, s in row["shapes"]]).BoundBox
        for _, _, glyph in row["shapes"]:
            glyph.translate(App.Vector((width - bounds.XLength) / 2 - bounds.XMin,
                                       margin - all_bounds.YMin, 0))
    backing = Part.makeBox(width, height, 2.4)
    coupon = backing.multiFuse(raised_rows(coupon_rows, config["relief_mm"])).removeSplitter()
    coupon_dir = PROPOSAL / "coupon"
    coupon_dir.mkdir(exist_ok=True)
    coupon = save_native(coupon, coupon_dir / "coupon.FCStd", config["coupon"]["part"],
                         [row["text"] for row in coupon_rows], config)
    coupon.exportStep(str(coupon_dir / "coupon.step"))
    coupon_triangles = export_stl(coupon, coupon_dir / "coupon.stl")
    actual_preview["coupon_top"] = face_data(Part.makeCompound(cap_faces(coupon, 3.6)))
    actual_preview["coupon_dimensions_mm"] = [width, height, 3.6]
    write_json(WORK / "actual-native-preview.json", actual_preview)
    report = {
        "revision": config["revision"], "status": config["status"],
        "lines": config["lines"], "units": "mm", "plate_dimensions_mm": [142, 40, 3.6],
        "reconstructed_current_symmetric_difference_mm3": original_difference,
        "carrier_symmetric_difference_mm3": carrier_difference,
        "native_saved_and_reopened": True, "step_reopened": True,
        "plate_native_volume_mm3": reread.Volume, "plate_stl_triangles": triangle_count,
        "candidate_native_top_equals_measured_glyphs": True,
        "coupon_dimensions_mm": [width, height, 3.6], "coupon_stl_triangles": coupon_triangles,
        "coupon_lines": [row["text"] for row in coupon_rows],
        "coupon_uses_same_glyph_solids_and_spacing": True,
        "coupon_source_character_ranges_inclusive": ranges,
        "physical_print_and_fit": "NOT_TESTED",
    }
    write_json(PROPOSAL / "cad-verification.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("outlines", "build"))
    args = parser.parse_args()
    config = json.loads((PROPOSAL / "config.json").read_text())
    require(config["lines"] == json.loads((ROOT / "source/personalization.json").read_text())["lines"],
            "The approved two display lines must remain unchanged.")
    WORK.mkdir(parents=True, exist_ok=True)
    if args.stage == "outlines":
        export_outlines(config)
    else:
        build(config)
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    os._exit(0)
