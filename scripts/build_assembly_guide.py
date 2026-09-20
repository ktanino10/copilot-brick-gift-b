"""Map actual print occurrences to interchangeable assembly locations, without changing geometry."""

import argparse
import base64
from collections import Counter, defaultdict
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
GUIDE_REVISION = "print-to-place-1"
CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def vector(value, size, label):
    require(isinstance(value, list) and len(value) == size
            and all(isinstance(n, (int, float)) and not isinstance(n, bool)
                    and math.isfinite(n) for n in value), f"Invalid {label}")
    return value


def safe_file(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "Expected a relative asset path")
    result = Path(root).resolve() / path
    require(result.resolve().is_relative_to(Path(root).resolve()), "Asset escapes its input root")
    require(result.is_file(), f"Missing input file: {path.name}")
    return result


def triangle_fingerprint(triangles):
    # 3MF stores six decimal places. Compare triangles independent of vertex/face ordering.
    points = np.rint(np.asarray(triangles) * 1000000).astype("<i8")
    require(points.ndim == 3 and points.shape[1:] == (3, 3), "Invalid triangle array")
    points = np.sort(points.view(np.dtype((np.void, 24))).reshape(-1, 3), axis=1)
    faces = np.sort(points.reshape(-1).view(np.dtype((np.void, 72))))
    return digest(faces.tobytes())


def load_mesh(path, spec):
    data = path.read_bytes()
    require(digest(data) == spec["sha256"], f"STL hash differs: {spec['id']}")
    require(len(data) >= 84, f"Truncated STL: {spec['id']}")
    count = struct.unpack_from("<I", data, 80)[0]
    require(count > 0 and len(data) == 84 + count * 50, "Expected the actual binary STL master")
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    triangles = np.frombuffer(data, dtype=dtype, count=count, offset=84)["vertices"].astype(float)
    require(bool(np.isfinite(triangles).all()), f"Non-finite STL coordinates: {spec['id']}")
    bounds = [triangles.min(axis=(0, 1)).tolist(), triangles.max(axis=(0, 1)).tolist()]
    require(np.allclose(bounds, spec["bounds"], atol=.0001, rtol=0), f"STL bounds differ: {spec['id']}")
    return {
        "encoding": "gzip-base64-stl", "sha256": digest(data), "bytes": len(data),
        "triangles": count, "payload": base64.b64encode(gzip.compress(data, mtime=0)).decode("ascii"),
    }, triangle_fingerprint(triangles)


def verify_plate(path, plate, fingerprints):
    with zipfile.ZipFile(path) as archive:
        node = ET.fromstring(archive.read("3D/3dmodel.model"))
    require(node.get("unit") == "millimeter", "3MF unit must be millimeter")
    resources = node.find(CORE + "resources")
    build = node.find(CORE + "build")
    require(resources is not None and build is not None, "3MF resources/build missing")
    objects = {}
    for obj in resources.findall(CORE + "object"):
        part = obj.get("name")
        require(part in fingerprints, f"Unexpected 3MF object: {part}")
        mesh = obj.find(CORE + "mesh")
        require(mesh is not None, "3MF must contain actual mesh objects")
        vertices = np.array([[float(v.get(axis)) for axis in "xyz"]
                             for v in mesh.find(CORE + "vertices")])
        faces = np.array([[int(t.get(key)) for key in ("v1", "v2", "v3")]
                          for t in mesh.find(CORE + "triangles")])
        require(len(vertices) > 0 and len(faces) > 0 and bool(np.isfinite(vertices).all()),
                "3MF contains invalid geometry")
        require(int(faces.min()) >= 0 and int(faces.max()) < len(vertices), "3MF vertex index out of range")
        require(triangle_fingerprint(vertices[faces]) == fingerprints[part], f"3MF/STL mesh differs: {part}")
        objects[obj.get("id")] = part
    require(len(build) == len(plate["items"]), f"3MF occurrence count differs: {plate['file']}")
    for printed, item in zip(build, plate["items"]):
        require(objects.get(printed.get("objectid")) == item["part"], "3MF slot order/part differs")
        values = [float(v) for v in printed.get("transform", "1 0 0 0 1 0 0 0 1 0 0 0").split()]
        expected = [1, 0, 0, 0, 1, 0, 0, 0, 1, *item["position"]]
        require(len(values) == 12 and np.allclose(values, expected, atol=.0000011, rtol=0),
                f"3MF print transform differs: {plate['file']}")
    return digest(path.read_bytes())


def build_mapping(catalog, assembly, manifest, mesh_root, plates_root, title=None):
    require(catalog["units"] == assembly["units"] == manifest["units"] == "mm", "All inputs must use mm")
    require(manifest["sliced"] is False and manifest["printer_settings_validated"] is False,
            "This guide describes unsliced, unvalidated print layouts")
    model_id = assembly["model"]
    require(isinstance(model_id, str) and ID.fullmatch(model_id), "Invalid model ID")
    models = [m for m in catalog["models"] if m["id"] == model_id]
    require(len(models) == 1, "Assembly must select exactly one catalog model")
    model = models[0]
    require(assembly["placements"] == model["placements"], "Catalog and assembly placements differ")
    require(assembly["steps"] == model["steps"], "Catalog and assembly steps differ")
    require(assembly["bounds"] == model["bounds"], "Catalog and assembly bounds differ")
    require(len(assembly["placements"]) == model["part_count"], "Assembly part count differs")
    palette = catalog["colors"]
    require(all(re.fullmatch(r"#[0-9a-fA-F]{6}", value["hex"]) for value in palette.values()),
            "Palette must use hex RGB")
    placements = []
    candidates = defaultdict(list)
    steps = assembly["steps"]
    require([s["number"] for s in steps] == list(range(1, len(steps) + 1)), "Step numbers must be continuous")
    step_ids = [pid for step in steps for pid in step["instances"]]
    require(step_ids == [p["id"] for p in assembly["placements"]], "Steps must order each placement exactly once")
    for index, item in enumerate(assembly["placements"]):
        require(ID.fullmatch(item["id"]) and ID.fullmatch(item["part"]), "Invalid placement/part ID")
        require(item["color"] in palette, "Unknown placement color")
        require(item["role"] in ("base_course", "front_module", "keeper", "face", "crest"),
                f"Unsupported insertion role: {item['role']}")
        require(item["id"] in steps[item["step"] - 1]["instances"], "Placement and step disagree")
        vector(item["position"], 3, "assembly position")
        vector(item["rotation"], 3, "assembly rotation")
        group = item["part"] + "|" + item["color"]
        copied = {key: item[key] for key in ("id", "part", "color", "position", "rotation", "step", "role")}
        copied.update(index=index, group=group)
        if "course" in item:
            copied["course"] = item["course"]
        if "module" in item:
            copied["module"] = item["module"]
        placements.append(copied)
        candidates[group].append(item["id"])
    require(len({p["id"] for p in placements}) == len(placements), "Duplicate placement ID")
    parts, meshes, fingerprints = {}, {}, {}
    for key in sorted({p["part"] for p in placements}):
        spec = catalog["parts"][key]
        require(spec["id"] == key, "Catalog part ID differs")
        for bound in spec["bounds"]:
            vector(bound, 3, "mesh bounds")
        meshes[key], fingerprints[key] = load_mesh(safe_file(mesh_root, spec["stl"]), spec)
        parts[key] = {field: spec[field] for field in ("id", "kind", "bounds", "sha256", "orientation")}
        parts[key]["dimensions"] = [round(b - a, 4) for a, b in zip(*spec["bounds"])]
        if "optional_color_change_z" in spec:
            parts[key]["finish_color"] = spec["letter_color"]
            parts[key]["color_change_z_mm"] = spec["optional_color_change_z"]
    assembly_counts = Counter((p["part"], p["color"]) for p in placements)
    bom_counts = Counter()
    for row in assembly["bom"]:
        bom_counts[row["part"], row["color"]] += row["quantity"]
    require(assembly_counts == bom_counts, "Assembly BOM/count differs")
    print_counts = Counter((item["part"], plate["color"]) for plate in manifest["plates"] for item in plate["items"])
    require(print_counts == assembly_counts, "Print occurrences must match assembly part+color quantities exactly")
    require(len({p["file"] for p in manifest["plates"]}) == len(manifest["plates"]), "Duplicate plate filename")
    used, sources, plates = Counter(), defaultdict(list), []
    for plate in manifest["plates"]:
        filename = plate["file"]
        require(ID.fullmatch(filename) and filename.endswith(".3mf"), "Invalid plate filename")
        sha = verify_plate(safe_file(plates_root, filename), plate, fingerprints)
        printed = {"file": filename, "color": plate["color"], "sha256": sha, "slots": []}
        if plate.get("finish_color"):
            printed["finish_color"] = plate["finish_color"]
            printed["manual_change_after_z_mm"] = float(plate["manual_change_after_z_mm"])
        for number, item in enumerate(plate["items"], 1):
            vector(item["position"], 3, "print position")
            vector(item["brim_box"], 4, "brim bounds")
            group = item["part"] + "|" + plate["color"]
            assigned = candidates[group][used[group]]
            used[group] += 1
            slot_id = f"{filename}#{number}"
            slot = {
                "id": slot_id, "number": number, "part": item["part"], "group": group,
                "print_position": item["position"], "print_rotation": [0, 0, 0], "brim_box": item["brim_box"],
                "suggested_placement": assigned, "candidate_placements": candidates[group],
            }
            printed["slots"].append(slot)
            sources[group].append({"plate": filename, "slot": number, "slot_id": slot_id, "suggested_placement": assigned})
        plates.append(printed)
    groups = {key: {"part": key.split("|")[0], "color": key.split("|")[1],
                    "placements": candidates[key], "sources": sources[key], "quantity": len(candidates[key])}
              for key in sorted(candidates)}
    for p in placements:
        p["suggested_source"] = next(s for s in sources[p["group"]] if s["suggested_placement"] == p["id"])
    mapped_steps = []
    for step in steps:
        members = [p for p in placements if p["step"] == step["number"]]
        source_files = sorted({source["plate"] for p in members for source in sources[p["group"]]})
        mapped_steps.append({**step, "first_index": members[0]["index"] if members else len(placements),
                             "end_index": members[-1]["index"] + 1 if members else len(placements),
                             "available_source_files": source_files})
    base_groups = {p["group"] for p in placements if p["role"] == "base_course"}
    presentation = model["presentation"]
    mapping = {
        "schema_version": 1, "guide_revision": GUIDE_REVISION, "geometry_revision": catalog["revision"],
        "model": model_id, "title": title or f"{model_id} / 印刷ファイルから組み立てる3Dガイド",
        "units": "mm", "sliced": False, "physical_fit_tested": False, "slot_numbers_are_physical_markings": False,
        "assignment": "Stable guide-only assignment; identical part+color copies are interchangeable.",
        "bed_mm": manifest["bed_nominal"], "bounds": assembly["bounds"], "part_count": len(placements),
        "colors": {k: {"hex": v["hex"], "name": v.get("name_ja", k)} for k, v in palette.items()},
        "parts": parts, "placements": placements, "plates": plates, "groups": groups, "steps": mapped_steps,
        "base_source_files": sorted({s["plate"] for key in base_groups for s in sources[key]}),
        "first_source": placements[0]["suggested_source"],
        "motion": {"module_lift_mm": presentation["plaque_release_mm"],
                   "module_front_mm": max(32, presentation["plaque_front_clearance_mm"] + 18),
                   "keeper_lift_mm": max(16, presentation["keeper_release_mm"])},
    }
    return mapping, meshes


def write_guide(mapping, meshes, output, runtime, template_dir, standalone=False):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    mapping_path = output.with_suffix(".mapping.json")
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    template_dir = Path(template_dir)
    template = (template_dir / "template.html").read_text()
    css = (template_dir / "style.css").read_text()
    javascript = Path(runtime).read_text()
    require("</script" not in javascript.lower(), "Bundle contains an unsafe HTML script delimiter")
    payload = json.dumps({"mapping": mapping, "meshes": meshes}, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    if standalone:
        styles = f"<style>{css}</style>"
        script = f"<script>{javascript}</script>"
    else:
        (output.parent / "runtime.js").write_text(javascript)
        (output.parent / "style.css").write_text(css)
        styles = f'<link rel="stylesheet" href="style.css?rev={GUIDE_REVISION}">'
        script = f'<script src="runtime.js?rev={GUIDE_REVISION}"></script>'
    replacements = {"TITLE": html.escape(mapping["title"]), "STYLE": styles, "DATA": payload, "SCRIPT": script}
    for key, value in replacements.items():
        marker = "@@" + key + "@@"
        require(marker in template, f"Missing template token: {key}")
        template = template.replace(marker, value)
    require(not re.search(r"@@[A-Z]+@@", template), "Unexpanded guide template token")
    output.write_text(template, encoding="utf-8")
    return mapping_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("catalog", "assembly", "plates", "mesh-root", "plates-root", "output"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--runtime", type=Path, default=ROOT / "build/assembly-guide/runtime.js")
    parser.add_argument("--template-dir", type=Path, default=ROOT / "web/assembly-guide")
    parser.add_argument("--title", help="Plain-text title; never interpreted as HTML.")
    parser.add_argument("--standalone", action="store_true", help="Embed classic runtime and CSS for one-file offline use.")
    args = parser.parse_args()
    mapping, meshes = build_mapping(read_json(args.catalog), read_json(args.assembly), read_json(args.plates),
                                    args.mesh_root, args.plates_root, args.title)
    mapping["inputs_sha256"] = {key: digest(getattr(args, key).read_bytes()) for key in ("catalog", "assembly", "plates")}
    result = write_guide(mapping, meshes, args.output, args.runtime, args.template_dir, args.standalone)
    print(f"PASS {mapping['model']}: {mapping['part_count']} exact occurrences, "
          f"{len(mapping['plates'])} real 3MF layouts; {result.name}; no print geometry modified.")


if __name__ == "__main__":
    main()
