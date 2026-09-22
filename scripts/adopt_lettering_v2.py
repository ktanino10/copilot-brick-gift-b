"""Promote the approved plate only; keep an explicitly labeled historical plate."""

import hashlib
import json
from pathlib import Path
import shutil

from write_single_3mf import write_single_3mf

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "proposals/plate-legibility-v2"
HISTORY = ROOT / "revisions/4.0-B-personal-kit.2"
REVISION = "4.1-B-legibility.1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    if HISTORY.exists():
        raise FileExistsError("The pre-adoption archive already exists; do not replace its history.")
    config = json.loads((PROPOSAL / "config.json").read_text())
    geometry = json.loads((PROPOSAL / "cad-verification.json").read_text())
    motion = json.loads((PROPOSAL / "motion-verification.json").read_text())
    if motion["status"] != "PASS_DIGITAL_CANDIDATE_ONLY" or geometry["carrier_symmetric_difference_mm3"] != 0:
        raise ValueError("Approve and verify the exact candidate before promoting it.")
    if not (PROPOSAL / "approval.json").is_file():
        raise ValueError("No recorded approval.")
    archive_files = {
        "nameplate/plate.stl": "kit/B/parts/NP3-TEXT-B.stl",
        "nameplate/plate.3mf": "kit/B/plates/B-black-to-white-z2p4-01.3mf",
        "nameplate/plate.FCStd": "source/native/NP3-TEXT-B.FCStd",
        "nameplate/plate.step": "source/native/NP3-TEXT-B.step",
        "nameplate/drawing.svg": "kit/B/drawings/parts/NP3-TEXT-B.svg",
        "parameters.json": "source/design/parameters.json",
    }
    HISTORY.mkdir(parents=True)
    for destination, original in archive_files.items():
        path = HISTORY / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / original, path)
    baseline = {
        "revision": "4.0-B-personal-kit.2", "status": "HISTORICAL_NOT_CURRENT",
        "plate_sha256": sha(ROOT / "kit/B/parts/NP3-TEXT-B.stl"),
        "unchanged_part_sha256": {
            path.name: sha(path) for path in sorted((ROOT / "kit/B/parts").glob("*.stl"))
            if path.stem != "NP3-TEXT-B"
        },
        "unchanged_plate_sha256": {
            path.name: sha(path) for path in sorted((ROOT / "kit/B/plates").glob("*.3mf"))
            if path.name != "B-black-to-white-z2p4-01.3mf"
        },
        "placements": json.loads((ROOT / "kit/B/assembly.json").read_text())["placements"],
        "bom_sha256": sha(ROOT / "kit/B/bom.csv"),
        "files": {name: sha(HISTORY / name) for name in archive_files},
    }
    write_json(HISTORY / "manifest.json", baseline)
    backup = ROOT / ".work/plate-v2/B-before.FCStd"
    if backup.exists():
        raise FileExistsError("Native baseline backup already exists.")
    shutil.copyfile(ROOT / "source/native/B.FCStd", backup)
    shutil.copyfile(PROPOSAL / "resources/BarlowCondensed-Bold.ttf",
                    ROOT / "source/resources/fonts/barlow-condensed/BarlowCondensed-Bold.ttf")
    shutil.copyfile(PROPOSAL / "letter-plan.json", ROOT / "source/design/nameplate-plan.json")
    shutil.copyfile(PROPOSAL / "candidate/plate.stl", ROOT / "kit/B/parts/NP3-TEXT-B.stl")
    write_single_3mf(ROOT / "kit/B/parts/NP3-TEXT-B.stl",
                     ROOT / "kit/B/plates/B-black-to-white-z2p4-01.3mf", "NP3-TEXT-B")
    sample = ROOT / "samples/nameplate-v2"
    sample.mkdir(parents=True, exist_ok=True)
    sample_id = "NP3-LETTER-TEST-B-V2"
    shutil.copyfile(PROPOSAL / "coupon/coupon.stl", sample / f"{sample_id}.stl")
    sample_layout = write_single_3mf(sample / f"{sample_id}.stl", sample / f"{sample_id}.3mf", sample_id)
    write_json(sample / "manifest.json", {
        "revision": REVISION, "part": sample_id, "quantity": 1,
        "included_in_assembly_bom": False, "sliced": False, "pause_encoded": False,
        "dimensions_mm": geometry["coupon_dimensions_mm"], "lines": geometry["coupon_lines"],
        "black_height_mm": 2.4, "white_relief_mm": 1.2, "source_rows": [1, 2],
        "source_character_ranges_inclusive": config["coupon"]["source_character_ranges_inclusive"],
        **sample_layout, "files": {
            f"{sample_id}.stl": sha(sample / f"{sample_id}.stl"),
            f"{sample_id}.3mf": sha(sample / f"{sample_id}.3mf"),
        },
    })
    parameters = json.loads((ROOT / "source/design/parameters.json").read_text())
    parameters["revision"] = REVISION
    parameters["message"].update({
        "relief": 1.2, "line_bottoms": [22, 7], "minimum_straight_stroke": 1.0,
        "lettering_strategy": "legibility-v2", "lettering_plan": "design/nameplate-plan.json",
        "row_fonts": [
            "resources/fonts/barlow-condensed/BarlowCondensed-Bold.ttf",
            "resources/fonts/barlow-condensed/BarlowCondensed-Black.ttf",
        ],
        "row_scale_modes": ["retain_x", "uniform"],
        "font": "resources/fonts/barlow-condensed/BarlowCondensed-Bold.ttf",
    })
    parameters["variants"][0]["text_heights"] = [12, 10]
    write_json(ROOT / "source/design/parameters.json", parameters)
    catalog = json.loads((ROOT / "source/design/catalog.json").read_text())
    catalog["revision"] = REVISION
    catalog["parameters_sha256"] = sha(ROOT / "source/design/parameters.json")
    catalog["message"] = parameters["message"]
    catalog["parts"]["NP3-TEXT-B"].update({
        "text_heights": [12, 10], "bounds": [[0, 0, 0], [142, 40, 3.6]],
        "volume_mm3": geometry["plate_native_volume_mm3"],
        "mesh_triangles": geometry["plate_stl_triangles"], "mesh_linear_deflection_mm": .0125,
        "sha256": sha(ROOT / "kit/B/parts/NP3-TEXT-B.stl"), "lettering_revision": "legibility-v2",
    })
    catalog["models"][0].update({
        "text_heights": [12, 10], "bounds": [[.1, -.3, 0], [191.9, 79.9, 238.6]],
        "actual_mm": [191.8, 80.2, 238.6],
    })
    write_json(ROOT / "source/design/catalog.json", catalog)
    interface = json.loads((ROOT / "source/design/interface.json").read_text())
    interface["revision"] = REVISION
    interface["message"] = parameters["message"]
    write_json(ROOT / "source/design/interface.json", interface)
    assembly = json.loads((ROOT / "kit/B/assembly.json").read_text())
    assembly["bounds"] = catalog["models"][0]["bounds"]
    write_json(ROOT / "kit/B/assembly.json", assembly)
    manifest = json.loads((ROOT / "kit/B/plates/manifest.json").read_text())
    manifest["revision"] = REVISION
    manifest["nameplate"].update({
        "lettering_revision": "legibility-v2", "ink_heights_mm": [12, 10],
        "black_support_mm": 2.4, "white_relief_mm": 1.2, "total_thickness_mm": 3.6,
    })
    write_json(ROOT / "kit/B/plates/manifest.json", manifest)
    print("Promoted exactly one STL/3MF and preserved the historical plate. Native/diagram update is the next required stage.")


if __name__ == "__main__":
    main()
