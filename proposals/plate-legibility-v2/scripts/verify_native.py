"""Check only the candidate replacement, unchanged carrier and release envelopes."""

import hashlib
import json
import os
from pathlib import Path
import sys

import FreeCAD as App
import Part

PROPOSAL = Path(__file__).resolve().parents[1]
ROOT = PROPOSAL.parents[1]
sys.path.insert(0, str(ROOT / "source/scripts"))
from freecad_geometry import bounds_list
from front_nameplate import carrier


def require(condition, message):
    if not condition:
        raise ValueError(message)


def symmetric_difference(a, b):
    return a.cut(b).Volume + b.cut(a).Volume


def possible_intersection(a, b):
    left = a.optimalBoundingBox(False, False)
    right = b.optimalBoundingBox(False, False)
    return all(min(x, y) > max(u, v) + 1e-7 for x, y, u, v in (
        (left.XMax, right.XMax, left.XMin, right.XMin),
        (left.YMax, right.YMax, left.YMin, right.YMin),
        (left.ZMax, right.ZMax, left.ZMin, right.ZMin),
    ))


def check_against(label, shape, others):
    volumes = {}
    for identifier, other in others:
        if possible_intersection(shape, other):
            volumes[identifier] = shape.common(other).Volume
    maximum = max(volumes.values(), default=0)
    require(maximum < 1e-5, f"Candidate collision during {label}: {volumes}")
    return {"stage": label, "candidate_pairs": len(volumes),
            "maximum_intersection_mm3": maximum, "checked_ids": list(volumes)}


def envelope(shape, vector):
    b = shape.optimalBoundingBox(False, False)
    minima = [min(value, value + delta) for value, delta in zip((b.XMin, b.YMin, b.ZMin), vector)]
    maxima = [max(value, value + delta) for value, delta in zip((b.XMax, b.YMax, b.ZMax), vector)]
    return Part.makeBox(*[upper - lower for lower, upper in zip(minima, maxima)], App.Vector(*minima))


def main():
    config = json.loads((PROPOSAL / "config.json").read_text())
    paths = [
        ROOT / "source/native/B.FCStd",
        ROOT / "revisions/4.0-B-personal-kit.2/nameplate/plate.FCStd",
        PROPOSAL / "candidate/plate.FCStd",
        PROPOSAL / "coupon/coupon.FCStd",
    ]
    before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    assembly = App.openDocument(str(paths[0]))
    old_document = App.openDocument(str(paths[1]))
    candidate_document = App.openDocument(str(paths[2]))
    coupon_document = App.openDocument(str(paths[3]))
    objects = [obj for obj in assembly.Objects if hasattr(obj, "PartID")]
    require(len(objects) == 150, "Unexpected production assembly object count.")
    target = next(obj for obj in objects if obj.PartID == "NP3-TEXT-B")
    candidate_object = candidate_document.getObject("Candidate")
    require(json.loads(candidate_object.DisplayLines) == config["lines"], "Candidate display lines changed.")
    candidate = candidate_object.Shape.copy()
    require(candidate.isValid() and len(candidate.Solids) == 1 and candidate.Volume > 0, "Invalid candidate native.")
    require(bounds_list(candidate) == [[0, 0, 0], [142, 40, 3.6]], "Candidate dimensions differ.")
    old = old_document.getObject("ReplacementPlate").Shape.copy()
    clip = Part.makeBox(160, 60, 2.4, App.Vector(-5, -5, 0))
    black_old, black_new = old.common(clip), candidate.common(clip)
    difference = symmetric_difference(black_old, black_new)
    require(difference < 1e-6, "Carrier or mounting geometry changed.")
    exported_carrier = Part.read(str(PROPOSAL / "candidate/unchanged-carrier.brep"))
    require(symmetric_difference(black_old, exported_carrier) < 1e-6, "Carrier BREP differs.")
    parameters = json.loads((ROOT / "source/design/parameters.json").read_text())
    settings = {**parameters["message"], "width": 142}
    canonical_carrier = carrier(settings)
    require(symmetric_difference(black_old, canonical_carrier) < 1e-6,
            "Canonical carrier does not match the original native.")

    candidate.Placement = App.Placement(target.Placement)
    remaining = [(obj.InstanceID, obj.Shape) for obj in objects if obj is not target]
    stages = [check_against("installed_candidate_vs149_parts", candidate, remaining)]
    keepers = [obj for obj in objects if obj.InstanceID in ("B-022", "B-023")]
    require(len(keepers) == 2, "Expected exactly two independently removable text keepers.")
    parked = []
    for keeper in keepers:
        stages.append(check_against(f"{keeper.InstanceID}_up6",
                                   envelope(keeper.Shape, (0, 0, 6)), [("candidate", candidate)]))
        up = keeper.Shape.copy()
        up.translate(App.Vector(0, 0, 6))
        stages.append(check_against(f"{keeper.InstanceID}_forward32_after_up6",
                                   envelope(up, (0, -32, 0)), [("candidate", candidate)]))
        up.translate(App.Vector(0, -32, 0))
        parked.append((keeper.InstanceID + "_parked", up))
    stationary = [(identifier, shape) for identifier, shape in remaining
                  if identifier not in ("B-022", "B-023")]

    # The carrier is a ruled loft of rectangles: extending local YMax sweeps it exactly upward.
    black_sweep = carrier({**settings, "height": 85})
    black_sweep.Placement = App.Placement(target.Placement)
    stages.append(check_against("continuous_carrier_lift0_to45", black_sweep, stationary + parked))
    # This full face slab contains all lettering, including holes and every intermediate lift position.
    white_sweep = Part.makeBox(138, 85, 1.2, App.Vector(2, 0, 2.4))
    white_sweep.Placement = App.Placement(target.Placement)
    stages.append(check_against("continuous_white_relief_lift0_to45_conservative_envelope",
                               white_sweep, stationary + parked))
    lifted = candidate.copy()
    lifted.translate(App.Vector(0, 0, 45))
    stages.append(check_against("continuous_forward0_to14_after_lift45",
                               envelope(lifted, (0, -14, 0)), stationary + parked))

    coupon = coupon_document.getObject("Candidate")
    expected_coupon_lines = [
        text[first:last + 1] for text, (first, last) in zip(
            config["lines"], config["coupon"]["source_character_ranges_inclusive"]
        )
    ]
    require(json.loads(coupon.DisplayLines) == expected_coupon_lines, "Coupon uses different substrings.")
    require(coupon.Shape.isValid() and len(coupon.Shape.Solids) == 1, "Invalid coupon native.")
    native_step_reports = {}
    for name, shape in (("candidate/plate", candidate_object.Shape), ("coupon/coupon", coupon.Shape)):
        step = Part.read(str(PROPOSAL / f"{name}.step"))
        require(step.isValid() and len(step.Solids) == 1 and abs(step.Volume - shape.Volume) < 1e-5,
                f"STEP and native differ: {name}")
        native_step_reports[name] = {"valid": True, "volume_difference_mm3": abs(step.Volume - shape.Volume)}
    bounds = bounds_list(Part.makeCompound([candidate, *[shape for _, shape in remaining]]))
    require(bounds == [[.1, -.3, 0], [191.9, 79.9, 238.6]], "Unexpected substituted assembly envelope.")
    for document in (coupon_document, candidate_document, old_document, assembly):
        App.closeDocument(document.Name)
    require(before == {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                       for relative in before}, "A native input was modified during read-only checks.")
    report = {
        "status": "PASS_DIGITAL_CANDIDATE_ONLY", "revision": config["revision"],
        "freecad_version": ".".join(App.Version()[:3]),
        "native_file_sha256": before, "files_modified": False,
        "lines": config["lines"], "black_support_mm": 2.4, "white_relief_mm": 1.2,
        "carrier_symmetric_difference_mm3": difference, "steps": stages,
        "native_step_checks": native_step_reports,
        "if_substituted_assembly_bounds_mm": bounds,
        "if_substituted_assembly_dimensions_mm": [191.8, 80.2, 238.6],
        "additional_forward_protrusion_mm": .4,
        "production_assembly_or_kit_updated": False,
        "release_scope": "Text keepers up6 then forward32, plaque up45 then forward14. Continuous conservative envelopes or exact ruled-loft sweep, not just discrete sampled poses. Place removed keepers aside before further handling.",
        "physical_fit_retention_strength": "NOT_TESTED",
    }
    (PROPOSAL / "motion-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    os._exit(0)
