"""Verify the approved mesh is the sole changed assembly master and all current views agree."""

import hashlib
import json
from pathlib import Path
import subprocess

from build_assembly_guide import triangle_fingerprint
from verify_kit import read_stl, require
from build_log_navigation import canonical_guide_hash

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = json.loads((ROOT / "revisions/4.0-B-personal-kit.2/manifest.json").read_text())
    assembly = json.loads((ROOT / "kit/B/assembly.json").read_text())
    require(assembly["placements"] == baseline["placements"] and len(assembly["placements"]) == 150,
            "An assembly placement changed.")
    require(sha(ROOT / "kit/B/bom.csv") == baseline["bom_sha256"], "The150-part BOM changed.")
    for name, expected in baseline["unchanged_part_sha256"].items():
        require(sha(ROOT / "kit/B/parts" / name) == expected, f"Non-text master changed:{name}")
    for name, expected in baseline["unchanged_plate_sha256"].items():
        require(sha(ROOT / "kit/B/plates" / name) == expected, f"Another print plate changed:{name}")
    approved = ROOT / "proposals/plate-legibility-v2/candidate/plate.stl"
    current = ROOT / "kit/B/parts/NP3-TEXT-B.stl"
    require(sha(approved) == sha(current), "The production plate differs from the approved comparison geometry.")
    sample = ROOT / "samples/nameplate-v2/NP3-LETTER-TEST-B-V2.stl"
    require(sha(sample) == sha(ROOT / "proposals/plate-legibility-v2/coupon/coupon.stl"),
            "The current coupon is not the exact approved full-scale glyph sample.")
    mesh, triangles = read_stl(current)
    coupon, _ = read_stl(sample)
    metrics = json.loads((ROOT / "verification/legibility-metrics.json").read_text())
    require([row["ink_height_mm"] for row in metrics["current_version"]] == [12, 10]
            and metrics["relief_mm"]["candidate"] == 1.2, "Measured lettering targets differ.")
    native = json.loads((ROOT / "verification/native.json").read_text())
    require(native["dimensions_mm"] == [191.8, 80.2, 238.6]
            and native["nameplate_dimensions_mm"] == [142, 40, 3.6]
            and native["assembly_plate_geometry_comparison"]["equal"], "Current native verification differs.")
    for filename, expected in native["native_files_sha256"].items():
        require(sha(ROOT / filename) == expected, f"Native changed after verification:{filename}")
    adoption = json.loads((ROOT / "verification/legibility-native-adoption.json").read_text())
    require(adoption["other_assembly_solids_geometry_identical"] == 149
            and adoption["assembly_step_valid_solids"] == 150
            and adoption["approved_plate_source_reproduced"], "Native/STEP adoption is incomplete.")
    motion = json.loads((ROOT / "verification/legibility-motion.json").read_text())
    require(motion["carrier_symmetric_difference_mm3"] == 0
            and all(row["maximum_intersection_mm3"] < 1e-5 for row in motion["steps"]),
            "Carrier or release-envelope check failed.")
    current_views = json.loads((ROOT / "verification/current-views.json").read_text())
    browser = json.loads((ROOT / "verification/guide-browser.json").read_text())
    entry_hash = sha(ROOT / "guide/index.html")
    require(current_views.get("canonical_guide_sha256", current_views["entry_sha256"])
            == browser.get("canonical_guide_sha256", browser["entry_sha256"])
            == canonical_guide_hash(ROOT / "guide/index.html"),
            "Current views and animation are not from the same new guide.")
    for name, record in current_views["captures"].items():
        require(sha(ROOT / "docs/images" / name) == record["sha256"], f"Stale current view:{name}")
    for name, expected in browser["media_files"].items():
        require(sha(ROOT / name) == expected, f"Stale assembly animation media:{name}")
    pdf = subprocess.check_output(["pdftotext", str(ROOT / "kit/B/drawings.pdf"), "-"], text=True)
    require(pdf.count("\f") == 54 and "TOTAL3.60" in pdf and "80.2" in pdf
            and "white relief1.2" in pdf and "github.com/tomokota" in pdf, "Current drawing PDF is stale.")
    report = {
        "revision": "4.1-B-legibility.1", "status": "PASS",
        "approved_plate_sha256": sha(current),
        "approved_plate_triangle_fingerprint": triangle_fingerprint(triangles),
        "coupon_sha256": sha(sample), "coupon_dimensions_mm": coupon.extents.tolist(),
        "unchanged_non_text_master_count": len(baseline["unchanged_part_sha256"]),
        "unchanged_other_print_plates": len(baseline["unchanged_plate_sha256"]),
        "unchanged_placements": 150, "unchanged_bom": True,
        "native_reopened": True, "assembly_step_valid_solids": 150,
        "plate_dimensions_mm": mesh.extents.tolist(), "assembly_dimensions_mm": [191.8, 80.2, 238.6],
        "actual_ink_heights_mm": [12, 10], "black_height_mm": 2.4, "white_height_mm": 1.2,
        "current_guide_sha256": entry_hash, "current_pdf_pages": 54,
        "new_design_physically_tested": False, "sliced": False,
    }
    (ROOT / "verification/legibility-release.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
