"""Replace only the approved nameplate in the real native assembly and its drawings."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import FreeCAD as App
import Part
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/scripts"))
from freecad_geometry import bounds_list
from front_nameplate import message_faces
from native_compare import compare_brep_geometry
from legible_lettering import face_data

PROPOSAL = ROOT / "proposals/plate-legibility-v2"
WORK = ROOT / ".work/plate-v2"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def setup_gui():
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("SaveThumbnail", False)
    App.ParamGet("User parameter:BaseApp/Preferences/General").SetString("AutoloadModule", "PartWorkbench")
    Gui.showMainWindow()
    Gui.getMainWindow().hide()


def rgb_faces(shape):
    return [(0.96, .95, .92) if face.CenterOfMass.z > 2.40001 else (.09, .11, .15)
            for face in shape.Faces]


def add_string(obj, name, value):
    if name not in obj.PropertiesList:
        obj.addProperty("App::PropertyString", name)
    setattr(obj, name, value)


def plate_drawing(shape):
    faces = [face for face in shape.Faces
             if face.BoundBox.ZLength < 1e-6 and abs(face.BoundBox.ZMin - 3.6) < 1e-6]
    paths = []
    for face in face_data(Part.makeCompound(faces)):
        rings = [face["outer"], *face["holes"]]
        path = " ".join("M " + " L ".join(f"{x:.6f},{y:.6f}" for x, y in ring) + " Z" for ring in rings)
        paths.append(f'<path d="{path}" fill="#f7f6ee" fill-rule="evenodd"/>')
    hull = "2,0 140,0 142,1.2 142,38.8 140,40 2,40 0,38.8 0,1.2"
    return {"width_mm": 142, "height_mm": 40,
            "svg": '<g transform="scale(1,-1)"><polygon points="' + hull
            + '" fill="#171d28"/>' + "".join(paths) + "</g>"}


def plate_section(shape, normal, offset, axes, width):
    lines = []
    for wire in shape.slice(App.Vector(*normal), offset):
        points = " ".join(f"{getattr(point, axes[0]):.6f},{getattr(point, axes[1]):.6f}"
                          for point in wire.discretize(Deflection=.002))
        lines.append(f'<polyline points="{points}" fill="none" stroke="#172433" stroke-width=".12"/>')
    return {"width_mm": width, "height_mm": 3.6,
            "svg": '<g transform="scale(1,-1)">' + "".join(lines) + "</g>"}


def sliced_polylines(objects, normal, distance, axes):
    result = []
    for obj in objects:
        shape = obj.Shape
        for wire in shape.slice(App.Vector(*normal), distance):
            result.append({
                "part": obj.PartID, "instance": obj.InstanceID,
                "points": [[getattr(point, axes[0]), getattr(point, axes[1])]
                           for point in wire.discretize(Deflection=.01)],
            })
    return result


def main(verify_saved=False):
    parameters = json.loads((ROOT / "source/design/parameters.json").read_text())
    catalog_path = ROOT / "source/design/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    lines = parameters["message"]["lines"]
    if not verify_saved:
        setup_gui()
    candidate_doc = App.openDocument(str(PROPOSAL / "candidate/plate.FCStd"))
    approved = candidate_doc.getObject("Candidate").Shape.copy()
    require(json.loads(candidate_doc.getObject("Candidate").DisplayLines) == lines, "Approval refers to different text.")
    print("Reconstructing approved glyph faces from the production source.", flush=True)
    measured = message_faces(catalog["parts"]["NP3-TEXT-B"], parameters)
    rebuilt_caps = Part.makeCompound([face for _, faces, _ in measured for face in faces])
    rebuilt_caps.translate(App.Vector(0, 0, 1.2))
    actual_caps = Part.makeCompound([
        face for face in approved.Faces
        if face.BoundBox.ZLength < 1e-6 and abs(face.BoundBox.ZMin - 3.6) < 1e-6
    ])
    difference = 0.0
    for face in rebuilt_caps.Faces:
        box = face.BoundBox
        possible = [
            other for other in actual_caps.Faces
            if min(box.XMax, other.BoundBox.XMax) > max(box.XMin, other.BoundBox.XMin)
            and min(box.YMax, other.BoundBox.YMax) > max(box.YMin, other.BoundBox.YMin)
        ]
        require(len(possible) == 1, "The approved glyph face mapping is not one-to-one.")
        other = possible[0]
        difference += face.cut(other).Area + other.cut(face).Area
    require(len(rebuilt_caps.Faces) == len(actual_caps.Faces) and difference < 1e-5,
            "Production source does not reproduce every approved glyph face.")
    print("Production glyphs match the approved native.", flush=True)
    App.closeDocument(candidate_doc.Name)

    if not verify_saved:
        plate_doc = App.newDocument("PrivateReplacementPlateV2")
        obj = plate_doc.addObject("Part::Feature", "ReplacementPlate")
        obj.Shape = approved
        require(obj.ViewObject is not None, "Native color serialization requires an initialized offscreen view provider.")
        add_string(obj, "PartID", "NP3-TEXT-B")
        add_string(obj, "PrivateDisplayLines", json.dumps(lines))
        add_string(obj, "Revision", parameters["revision"])
        add_string(obj, "Status", "APPROVED_DESIGN_NOT_SLICED_PHYSICAL_RESULT_UNVERIFIED")
        obj.ViewObject.ShapeColor = (.09, .11, .15)
        obj.ViewObject.DiffuseColor = rgb_faces(approved)
        plate_doc.recompute()
        plate_doc.saveAs(str(ROOT / "source/native/NP3-TEXT-B.FCStd"))
        approved.exportStep(str(ROOT / "source/native/NP3-TEXT-B.step"))
        App.closeDocument(plate_doc.Name)
    else:
        plate_doc = App.openDocument(str(ROOT / "source/native/NP3-TEXT-B.FCStd"))
        saved = plate_doc.getObject("ReplacementPlate")
        require(saved.PartID == "NP3-TEXT-B" and json.loads(saved.PrivateDisplayLines) == lines
                and compare_brep_geometry(saved.Shape, approved)["equal"],
                "The already-saved native does not match the approved plate.")
        App.closeDocument(plate_doc.Name)

    original = App.openDocument(str(WORK / "B-before.FCStd"))
    print("Reading the150-placement native baseline.", flush=True)
    objects = [item for item in original.Objects if hasattr(item, "PartID")]
    require(len(objects) == 150, "Unexpected baseline assembly.")
    before = {item.InstanceID: {
        "part": item.PartID, "placement": list(item.Placement.toMatrix().A),
        "brep": item.Shape.exportBrepToString(), "shape": item.Shape.copy(),
    } for item in objects}
    if not verify_saved:
        target = next(item for item in objects if item.PartID == "NP3-TEXT-B")
        placement = App.Placement(target.Placement)
        target.Shape = approved
        target.Placement = placement
        target.MessageLines = json.dumps(lines)
        target.ViewObject.DiffuseColor = rgb_faces(approved)
        add_string(target, "LetteringRevision", "legibility-v2")
        if original.getObject("Design"):
            add_string(original.getObject("Design"), "Revision", parameters["revision"])
        original.recompute()
        original.saveAs(str(ROOT / "source/native/B.FCStd"))
        import Import
        Import.export(objects, str(ROOT / "source/native/B.step"))
    App.closeDocument(original.Name)
    assembly = App.openDocument(str(ROOT / "source/native/B.FCStd"))
    objects = [item for item in assembly.Objects if hasattr(item, "PartID")]
    unchanged = 0
    byte_identical = 0
    serialization_only = []
    for item in objects:
        reference = before[item.InstanceID]
        require(item.PartID == reference["part"]
                and list(item.Placement.toMatrix().A) == reference["placement"],
                "A part ID or assembly transform changed.")
        if item.PartID != "NP3-TEXT-B":
            if item.Shape.exportBrepToString() == reference["brep"]:
                byte_identical += 1
            else:
                old_shape = reference["shape"]
                print(f"Verifying serialization-only geometry difference for{item.InstanceID}.", flush=True)
                require(compare_brep_geometry(old_shape, item.Shape)["equal"]
                        and bounds_list(old_shape) == bounds_list(item.Shape)
                        and len(old_shape.Faces) == len(item.Shape.Faces),
                        f"An unrelated native solid changed: {item.InstanceID}")
                serialization_only.append(item.InstanceID)
            unchanged += 1
    shape = Part.makeCompound([item.Shape for item in objects])
    require(bounds_list(shape) == [[.1, -.3, 0], [191.9, 79.9, 238.6]], "Updated assembly dimensions differ.")
    total_volume = sum(item.Shape.Volume for item in objects)
    catalog["models"][0]["cad_solid_volume_mm3"] = total_volume
    catalog["models"][0]["center_of_material_mm"] = [
        sum(item.Shape.Volume * getattr(item.Shape.Solids[0].CenterOfMass, axis) for item in objects) / total_volume
        for axis in ("x", "y", "z")
    ]
    catalog["parts"]["NP3-TEXT-B"]["local_center_mm"] = list(approved.Solids[0].CenterOfMass)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"Native replacement saved/reopened; {unchanged} other solids geometrically identical, "
          f"{byte_identical} BREP serializations byte-identical.", flush=True)

    projections = {
        "plate_top": plate_drawing(approved),
        "plate_front": plate_section(approved, (0, 1, 0), 26, ("x", "z"), 142),
        "plate_right": plate_section(approved, (1, 0, 0), 71, ("y", "z"), 40),
    }
    placements = {row["id"]: row for row in catalog["models"][0]["placements"]}
    base_objects = [item for item in objects if placements[item.InstanceID]["step"] <= 7]
    projections["front_section_z24"] = sliced_polylines(base_objects, (0, 0, 1), 24, ("x", "y"))
    projections["front_section_x40"] = sliced_polylines(base_objects, (1, 0, 0), 40, ("y", "z"))
    (WORK / "production-projections.json").write_text(json.dumps(projections) + "\n")
    print("Projected only the new plate caps and the affected native sections; whole-body views use the actual STL renderer.", flush=True)
    App.closeDocument(assembly.Name)
    step = Part.read(str(ROOT / "source/native/B.step"))
    require(step.isValid() and len(step.Solids) == 150, "Assembly STEP does not reopen as 150 valid solids.")
    require(abs(step.Volume - total_volume) < .001, "Assembly STEP volume differs from the native.")
    report = {
        "revision": parameters["revision"], "status": "PASS",
        "replaced_instance": "B-020", "replaced_part": "NP3-TEXT-B",
        "other_assembly_solids_geometry_identical": unchanged,
        "other_assembly_solids_brep_byte_identical": byte_identical,
        "serialization_roundoff_only_instances": serialization_only,
        "native_comparison_method": "Canonical cleaned BRep tokens, topology and analytic geometry; numeric tolerance1e-12. No coincident-solid Boolean needed.",
        "assembly_placements_unchanged": 150, "assembly_step_valid_solids": len(step.Solids),
        "assembly_step_volume_difference_mm3": abs(step.Volume - total_volume),
        "approved_plate_source_reproduced": True, "native_view_colors_preserved": True,
        "assembly_bounds_mm": [[.1, -.3, 0], [191.9, 79.9, 238.6]],
        "physical_print_and_fit": "NOT_TESTED",
    }
    (ROOT / "verification/legibility-native-adoption.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    os._exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-saved", action="store_true",
                        help="Verify and project already-saved approved natives without initializing the GUI.")
    main(parser.parse_args().verify_saved)
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    os._exit(0)
