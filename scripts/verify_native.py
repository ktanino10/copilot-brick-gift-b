#!/usr/bin/env python3
"""Reopen the adopted personal natives using FreeCAD's matching Python."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

import FreeCAD as App
import Part


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/scripts"))
from freecad_geometry import bounds_list, placement_for
from letter_metrics import straight_strokes

LINES = ["Same icon, New adventures", "github.com/tomokota"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-catalog-metadata", action="store_true")
    args = parser.parse_args()
    assembly_path = ROOT / "source/native/B.FCStd"
    plate_path = ROOT / "source/native/NP3-TEXT-B.FCStd"
    before = {str(path.relative_to(ROOT)): digest(path) for path in (assembly_path, plate_path)}
    assembly = json.loads((ROOT / "kit/B/assembly.json").read_text())
    document = App.openDocument(str(assembly_path))
    standalone = App.openDocument(str(plate_path))
    objects = [obj for obj in document.Objects if hasattr(obj, "PartID")]
    require(len(objects) == 150, "Native assembly must contain 150 printable objects.")
    expected = {row["id"]: row for row in assembly["placements"]}
    require({obj.InstanceID for obj in objects} == set(expected), "Native instance IDs differ.")
    require(Counter((obj.PartID, obj.ColorName) for obj in objects)
            == Counter((row["part"], row["color"]) for row in expected.values()),
            "Native part/color counts differ from assembly.")
    for obj in objects:
        row = expected[obj.InstanceID]
        require(obj.Shape.isValid() and len(obj.Shape.Solids) == 1 and obj.Shape.Volume > 0,
                f"Invalid native solid: {obj.InstanceID}")
        actual = obj.Placement.toMatrix().A
        planned = placement_for(row).toMatrix().A
        require(max(abs(a - b) for a, b in zip(actual, planned)) < 1e-8,
                f"Native placement differs: {obj.InstanceID}")
    compound = Part.makeCompound([obj.Shape for obj in objects])
    bounds = bounds_list(compound)
    require(bounds == assembly["bounds"], "Native assembly envelope differs.")
    require([round(b - a, 6) for a, b in zip(*bounds)] == [191.8, 79.8, 238.6],
            "Unexpected B assembly size.")
    target = next(obj for obj in objects if obj.PartID == "NP3-TEXT-B")
    require(json.loads(target.MessageLines) == LINES, "Assembly lettering metadata differs.")
    replacement = standalone.getObject("ReplacementPlate")
    require(replacement.PartID == "NP3-TEXT-B"
            and json.loads(replacement.PrivateDisplayLines) == LINES,
            "Standalone lettering metadata differs.")
    plate = replacement.Shape.copy()
    require(plate.isValid() and len(plate.Solids) == 1 and plate.Volume > 0,
            "Invalid standalone nameplate.")
    require(bounds_list(plate) == [[0, 0, 0], [142, 40, 3.2]], "Nameplate dimensions differ.")
    native_local = target.Shape.copy()
    native_local.Placement = App.Placement()
    difference = native_local.cut(plate).Volume + plate.cut(native_local).Volume
    require(difference < 1e-5, "Assembly plate and standalone personal plate differ.")
    step_shape = Part.read(str(ROOT / "source/native/NP3-TEXT-B.step"))
    require(step_shape.isValid() and len(step_shape.Solids) == 1, "Invalid personal STEP.")
    require(abs(step_shape.Volume - plate.Volume) < .001, "STEP and native volume differ.")
    cap_faces = [face for face in plate.Faces
                 if face.BoundBox.ZLength < 1e-5 and abs(face.BoundBox.ZMin - 3.2) < 1e-5]
    stroke = min(item["width_mm"] for item in straight_strokes(cap_faces))
    require(stroke >= .84, "The native straight-stroke requirement is not met.")

    maximum_overlap = 0.0
    candidates = 0
    for obj in objects:
        if obj is target:
            continue
        left = target.Shape.optimalBoundingBox(False, False)
        right = obj.Shape.optimalBoundingBox(False, False)
        if any(min(a, b) <= max(c, d) for a, b, c, d in (
            (left.XMax, right.XMax, left.XMin, right.XMin),
            (left.YMax, right.YMax, left.YMin, right.YMin),
            (left.ZMax, right.ZMax, left.ZMin, right.ZMin),
        )):
            continue
        candidates += 1
        maximum_overlap = max(maximum_overlap, target.Shape.common(obj.Shape).Volume)
    require(maximum_overlap < 1e-5, "Personal nameplate interferes with the assembly.")
    total_volume = sum(obj.Shape.Volume for obj in objects)
    center = [
        sum(obj.Shape.Volume * getattr(obj.Shape.Solids[0].CenterOfMass, axis)
            for obj in objects) / total_volume
        for axis in ("x", "y", "z")
    ]
    catalog_path = ROOT / "source/design/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    plate_bytes = (ROOT / "kit/B/parts/NP3-TEXT-B.stl").read_bytes()
    plate_metrics = {
        "text": LINES, "bounds": bounds_list(plate),
        "volume_mm3": round(plate.Volume, 6),
        "mesh_triangles": struct.unpack_from("<I", plate_bytes, 80)[0],
        "sha256": hashlib.sha256(plate_bytes).hexdigest(),
        "local_center_mm": list(plate.Solids[0].CenterOfMass),
    }
    if args.refresh_catalog_metadata:
        catalog["parts"]["NP3-TEXT-B"].update(plate_metrics)
        catalog["models"][0]["cad_solid_volume_mm3"] = total_volume
        catalog["models"][0]["center_of_material_mm"] = center
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    require(catalog["parts"]["NP3-TEXT-B"] | plate_metrics
            == catalog["parts"]["NP3-TEXT-B"], "Catalog still contains stale nameplate metadata.")
    require(abs(catalog["models"][0]["cad_solid_volume_mm3"] - total_volume) < 1e-5,
            "Catalog still contains stale assembly volume.")
    require(max(abs(a - b) for a, b in zip(catalog["models"][0]["center_of_material_mm"], center)) < 1e-5,
            "Catalog still contains stale assembly center metadata.")
    for opened in (standalone, document):
        App.closeDocument(opened.Name)
    require(before == {path: digest(ROOT / path) for path in before}, "Native files were modified.")
    report = {
        "status": "PASS", "freecad_version": ".".join(App.Version()[:3]),
        "native_files_sha256": before, "native_files_modified": False,
        "model": "B", "assembly_objects": 150, "steps": len(assembly["steps"]),
        "bounds_mm": bounds, "dimensions_mm": [191.8, 79.8, 238.6],
        "nameplate_lines": LINES, "nameplate_dimensions_mm": [142, 40, 3.2],
        "assembly_plate_symmetric_difference_mm3": difference,
        "nameplate_native_volume_mm3": plate.Volume,
        "minimum_measured_straight_stroke_mm": stroke,
        "nameplate_interference_candidates": candidates,
        "maximum_nameplate_intersection_mm3": maximum_overlap,
        "physical_fit_strength_stability": "NOT_TESTED", "sliced": False,
    }
    (ROOT / "verification/native.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False), file=sys.__stdout__, flush=True)


if __name__ == "__main__":
    main()
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    os._exit(0)
