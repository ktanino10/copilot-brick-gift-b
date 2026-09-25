#!/usr/bin/env python3
"""Targeted geometry, counts, offline links, privacy and ZIP verification."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import trimesh

from build_print_kit import ARCHIVE, REVISION, ROOT, payload_files
from verify_guide_mapping import verify_embedded, verify_mapping
from verify_offline_html import verify_file as verify_offline_html
from build_log_navigation import canonical_guide_hash
from verify_build_log import JournalDocument, USER_VIDEO_PAGE_URL, USER_VIDEO_URL, verify_user_video_link
from build_photo_log import PHOTO_BATCHES, PROGRESS_ANCHOR

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
LINES = ["Same icon, New adventures", "github.com/tomokota"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def read_stl(path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    require(len(data) == 84 + 50 * count, f"Not a binary STL of the declared size: {path.name}")
    records = np.frombuffer(data, dtype=np.dtype([
        ("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")
    ]), offset=84, count=count)
    triangles = records["vertices"].astype(np.float64)
    require(np.isfinite(triangles).all(), f"Nonfinite vertices: {path.name}")
    vertices, inverse = np.unique(triangles.reshape(-1, 3), axis=0, return_inverse=True)
    mesh = trimesh.Trimesh(vertices=vertices, faces=inverse.reshape(-1, 3), process=False)
    require(mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0,
            f"Mesh is not closed, consistently wound and positive-volume: {path.name}")
    require((mesh.area_faces > 0).all(), f"Degenerate triangle: {path.name}")
    verify_vertex_links(mesh, path.name)
    return mesh, triangles


def verify_vertex_links(mesh, name):
    links = [[] for _ in mesh.vertices]
    parents = list(range(len(mesh.vertices)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for a, b, c in mesh.faces.tolist():
        links[a].append((b, c))
        links[b].append((c, a))
        links[c].append((a, b))
        parents[root(a)] = root(b)
        parents[root(b)] = root(c)
    require(len({root(index) for index in range(len(parents))}) == 1,
            f"Mesh contains disconnected bodies: {name}")
    for pairs in links:
        adjacent = {}
        for a, b in pairs:
            adjacent.setdefault(a, []).append(b)
            adjacent.setdefault(b, []).append(a)
        require(all(len(values) == 2 for values in adjacent.values()),
                f"Nonmanifold vertex link: {name}")
        start = next(iter(adjacent))
        previous, current = None, start
        visited = set()
        while current not in visited:
            visited.add(current)
            choices = adjacent[current]
            following = choices[1] if choices[0] == previous else choices[0]
            previous, current = current, following
        require(current == start and len(visited) == len(adjacent),
                f"Pinched/nonmanifold vertex: {name}")


def check_3mf(path, expected, meshes, colors):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) == 3
                and set(names) == {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"},
                f"Unexpected 3MF members/settings: {path.name}")
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    require(model.attrib["unit"] == "millimeter", f"Wrong 3MF units: {path.name}")
    materials = {
        material.attrib["id"]: [base.attrib for base in material.findall("m:base", NS)]
        for material in model.findall("m:resources/m:basematerials", NS)
    }
    objects = {}
    for obj in model.findall("m:resources/m:object", NS):
        name = obj.attrib["name"]
        require(name in meshes, f"Unknown 3MF master: {name}")
        material = materials[obj.attrib["pid"]][int(obj.attrib["pindex"])]
        require(material["name"] == expected["color"]
                and material["displaycolor"].upper() == colors[expected["color"]]["hex"].upper() + "FF",
                f"3MF material color differs: {path.name}/{name}")
        vertices = np.array([[float(v.attrib[axis]) for axis in ("x", "y", "z")]
                             for v in obj.findall("m:mesh/m:vertices/m:vertex", NS)])
        faces = np.array([[int(t.attrib[axis]) for axis in ("v1", "v2", "v3")]
                          for t in obj.findall("m:mesh/m:triangles/m:triangle", NS)])
        reference = meshes[name][1]
        require(vertices[faces].shape == reference.shape
                and np.allclose(vertices[faces], reference, atol=1e-5, rtol=0),
                f"3MF geometry differs from its STL: {path.name}/{name}")
        objects[obj.attrib["id"]] = (name, vertices.min(axis=0), vertices.max(axis=0))
    items = model.findall("m:build/m:item", NS)
    require(len(items) == len(expected["items"]), f"3MF instance count differs: {path.name}")
    counts = Counter()
    boxes = []
    for item, planned in zip(items, expected["items"]):
        name, lower, upper = objects[item.attrib["objectid"]]
        require(name == planned["part"], f"3MF master order differs: {path.name}")
        transform = [float(value) for value in item.attrib["transform"].split()]
        require(np.allclose(transform[:9], [1, 0, 0, 0, 1, 0, 0, 0, 1], atol=1e-8)
                and np.allclose(transform[9:], planned["position"], atol=1e-6),
                f"3MF print transform differs: {path.name}")
        position = np.array(transform[9:])
        require(abs(lower[2] + position[2]) < 1e-6, f"Part not seated on Z=0: {path.name}")
        box = [lower[0] + position[0] - 6, lower[1] + position[1] - 6,
               upper[0] + position[0] + 6, upper[1] + position[1] + 6]
        require(np.allclose(box, planned["brim_box"], atol=2e-5), f"Brim envelope differs: {path.name}")
        require(min(box) >= 0 and max(box) <= 256, f"Nominal bed envelope exceeded: {path.name}")
        for other in boxes:
            require(min(box[2], other[2]) <= max(box[0], other[0])
                    or min(box[3], other[3]) <= max(box[1], other[1]),
                    f"Candidate brim envelopes intersect: {path.name}")
        boxes.append(box)
        counts[(name, expected["color"])] += 1
    require({name for name, _, _ in objects.values()} == {name for name, _ in counts},
            f"Unused/unexpected 3MF resources: {path.name}")
    return counts


def headings(path):
    result = set()
    repetitions = Counter()
    content = path.read_text()
    explicit = JournalDocument()
    explicit.feed(content)
    result.update(explicit.ids)
    for line in content.splitlines():
        if re.match(r"^#{1,6} ", line):
            text = re.sub(r"^#{1,6} ", "", line).lower()
            slug = re.sub(r"[^\w\s-]", "", text).replace(" ", "-")
            suffix = f"-{repetitions[slug]}" if repetitions[slug] else ""
            result.add(slug + suffix)
            repetitions[slug] += 1
    return result


def verify_links(creating_report=False):
    count = 0
    for path in [ROOT / "README.md", *ROOT.glob("docs/*.md"), *ROOT.glob("notices/*.md")]:
        for url in re.findall(r"\]\(([^)\s]+)\)", path.read_text()):
            parsed = urlsplit(url)
            if parsed.scheme:
                require(parsed.scheme == "https", f"Non-HTTPS document URL: {path.name}")
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            pending_report = creating_report and resolved == ROOT / "verification/kit.json"
            require(resolved.is_relative_to(ROOT) and (resolved.exists() or pending_report),
                    f"Broken relative link: {path.relative_to(ROOT)} -> {url}")
            if parsed.fragment and resolved.suffix == ".md":
                require(unquote(parsed.fragment) in headings(resolved),
                        f"Broken heading link: {path.name} -> {url}")
            count += 1
    return count


def privacy_scan():
    forbidden = re.compile(
        r"/(?:Users|home|Applications)/|file:\x2f\x2f|[A-Z]:\\Users\\|"
        r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
        r"AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    )
    for path in payload_files():
        if path.suffix in {".md", ".txt", ".csv", ".json", ".svg", ".py", ".step", ".html", ".js", ".mjs", ".css"}:
            text = path.read_text()
            require(not forbidden.search(text), f"Private path or credential-like value: {path.relative_to(ROOT)}")
            if path.is_relative_to(ROOT / "kit") or path.is_relative_to(ROOT / "source/design"):
                require("YOUR-USERNAME" not in text, f"Generic nameplate remains: {path.name}")
        if path.suffix == ".FCStd":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if name.endswith(".xml"):
                        text = archive.read(name).decode()
                        require(not forbidden.search(text) and "YOUR-USERNAME" not in text,
                                f"Unexpected native metadata: {path.name}/{name}")
        if path.suffix == ".svg":
            svg = ET.parse(path).getroot()
            require(not any(node.tag.endswith("}script") for node in svg.iter()),
                    f"Unexpected script in drawing: {path.name}")
    publication = json.loads((ROOT / "publication/policy.json").read_text())
    require(publication["repository"] == "ktanino10/copilot-brick-gift-b"
            and publication["repository_visibility"] == "public" and publication["pages_enabled"] is True,
            "Public distribution requires the explicit current publication policy.")
    workflow_dir = ROOT / ".github/workflows"
    workflow_files = {path.name for path in workflow_dir.iterdir() if path.is_file()} if workflow_dir.exists() else set()
    require(workflow_files <= {"pages.yml"} and not (ROOT / "CNAME").exists(),
            "Only the specifically authorized recipient Pages workflow may be present.")


def verify_package():
    files = payload_files()
    listed = {}
    for line in (ROOT / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name not in listed, f"Duplicate checksum entry: {name}")
        listed[name] = digest
    require(set(listed) == {path.relative_to(ROOT).as_posix() for path in files},
            "Delivery checksum inventory differs.")
    for name, digest in listed.items():
        require(sha((ROOT / name).read_bytes()) == digest, f"File checksum differs: {name}")
    expected = {path.relative_to(ROOT).as_posix() for path in files} | {"SHA256SUMS.txt"}
    with zipfile.ZipFile(ARCHIVE) as archive:
        require(archive.testzip() is None, "ZIP CRC failure.")
        names = archive.namelist()
        require(len(names) == len(set(names)) and set(names) == expected,
                "Offline ZIP members missing, duplicated or unexpected.")
        require(not any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names),
                "Unsafe ZIP paths.")
        for name in names:
            require(archive.read(name) == (ROOT / name).read_bytes(), f"ZIP content differs: {name}")
        require(sum(name.endswith(".stl") for name in names) == 35, "ZIP must contain 34 original masters plus1 lettering coupon.")
        require(sum(name.endswith(".3mf") for name in names) == 15, "ZIP must contain 14 assembly plates plus1 lettering coupon.")
        require("guide/index.html" in names, "ZIP is missing the offline 3D guide entry.")
        journal = JournalDocument()
        journal.feed(archive.read("docs/BUILD-LOG.html").decode("utf-8"))
        verify_user_video_link(journal)
        for link in journal.links + [image["src"] for image in journal.images]:
            if link in (USER_VIDEO_URL, USER_VIDEO_PAGE_URL):
                continue
            path = link.split("#")[0]
            target = posixpath.normpath(posixpath.join("docs", path)) if path else "docs/BUILD-LOG.html"
            require(target in names, f"Offline journal target is missing from ZIP:{target}")
        require(not any(name.endswith(".zip") for name in names), "No nested duplicate kits.")
    digest, filename = (ROOT / "downloads/SHA256SUMS.txt").read_text().strip().split("  ", 1)
    require(filename == ARCHIVE.name and digest == sha(ARCHIVE.read_bytes()), "ZIP checksum differs.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    assembly = json.loads((ROOT / "kit/B/assembly.json").read_text())
    catalog = json.loads((ROOT / "source/design/catalog.json").read_text())
    bom = read_csv(ROOT / "kit/B/bom.csv")
    expected = Counter({(row["part"], row["color"]): int(row["quantity"]) for row in bom})
    require(len(bom) == len(expected) == 23 and sum(expected.values()) == 150, "BOM differs.")
    require(Counter((row["part"], row["color"]) for row in assembly["placements"]) == expected,
            "Assembly counts differ from BOM.")
    require(len({row["part"] for row in bom}) == 21, "B must have 21 masters.")
    require(catalog["message"]["lines"] == LINES
            and [model["id"] for model in catalog["models"]] == ["B"], "Private catalog scope differs.")
    require(catalog["parameters_sha256"] == sha((ROOT / "source/design/parameters.json").read_bytes()),
            "Parameter hash differs from catalog.")
    meshes = {}
    mesh_reports = []
    for path in sorted((ROOT / "kit").rglob("*.stl")):
        mesh, triangles = read_stl(path)
        require(path.stem not in meshes, f"Duplicate STL master: {path.name}")
        require(np.allclose(mesh.bounds, catalog["parts"][path.stem]["bounds"], atol=2e-5, rtol=0),
                f"STL bounds differ from catalog: {path.name}")
        require(abs(mesh.bounds[0, 2]) < 1e-6, f"STL is not on bed: {path.name}")
        require(sha(path.read_bytes()) == catalog["parts"][path.stem]["sha256"], f"Master hash differs: {path.name}")
        meshes[path.stem] = (mesh, triangles)
        mesh_reports.append({"file": path.relative_to(ROOT).as_posix(), "sha256": sha(path.read_bytes()),
                             "triangles": len(mesh.faces), "bounds_mm": mesh.bounds.tolist(),
                             "closed": True, "vertex_manifold": True, "connected_bodies": 1,
                             "positive_volume_mm3": float(mesh.volume)})
    require(len(meshes) == 34, "Expected only 21 B + 12 fit + 1 extra trial masters.")
    require(set(meshes) == set(catalog["parts"]), "Catalog master selection differs.")
    require(np.allclose(meshes["NP3-TEXT-B"][0].extents, [142, 40, 3.6], atol=1e-5), "Plate size differs.")
    manifest = json.loads((ROOT / "kit/B/plates/manifest.json").read_text())
    require(manifest["nameplate"]["lines"] == LINES and manifest["sliced"] is False
            and manifest["pause_encoded"] is False and manifest["printer_settings_validated"] is False,
            "Plate status or personalization differs.")
    require(len(manifest["plates"]) == 14
            and {row["file"] for row in manifest["plates"]} == {p.name for p in (ROOT / "kit/B/plates").glob("*.3mf")},
            "Unexpected plate files.")
    actual = Counter()
    for plate in manifest["plates"]:
        for item in plate["items"]:
            finish, height = ("white", 2.4) if item["part"] == "NP3-TEXT-B" else (
                ("white", 2.8) if item["part"] == "NP3-LOGO-B" else ("", "")
            )
            require((plate["finish_color"], plate["manual_change_after_z_mm"]) == (finish, height),
                    "A body or front plate has the wrong color-change guidance.")
        actual.update(check_3mf(ROOT / "kit/B/plates" / plate["file"], plate, meshes, catalog["colors"]))
    require(actual == expected, "3MF aggregate part/color counts differ from BOM.")
    sample_root = ROOT / "samples/nameplate-v2"
    sample = json.loads((sample_root / "manifest.json").read_text())
    require(sample["part"] == "NP3-LETTER-TEST-B-V2" and sample["quantity"] == 1
            and sample["included_in_assembly_bom"] is False and sample["sliced"] is False
            and sample["pause_encoded"] is False and sample["white_relief_mm"] == 1.2
            and sample["black_height_mm"] == 2.4, "Lettering sample contract differs.")
    sample_mesh, sample_triangles = read_stl(sample_root / (sample["part"] + ".stl"))
    require(np.allclose(sample_mesh.extents, sample["dimensions_mm"], atol=2e-5),
            "Lettering sample dimensions differ.")
    for filename, expected_hash in sample["files"].items():
        require(sha((sample_root / filename).read_bytes()) == expected_hash, "Lettering sample hash differs.")
    position = sample["position"]
    lower, upper = sample_mesh.bounds
    brim = [lower[0] + position[0] - 6, lower[1] + position[1] - 6,
            upper[0] + position[0] + 6, upper[1] + position[1] + 6]
    sample_counts = check_3mf(
        sample_root / (sample["part"] + ".3mf"),
        {"color": "black", "items": [{"part": sample["part"], "position": position, "brim_box": brim}]},
        {sample["part"]: (sample_mesh, sample_triangles)}, catalog["colors"],
    )
    require(sample_counts == Counter({(sample["part"], "black"): 1}), "Expected one separate lettering sample.")
    trial = read_csv(ROOT / "kit/trial/bom.csv")
    require({row["part"]: int(row["quantity"]) for row in trial} == {
        "BR-02x02-H096": 2, "BR-02x04-H096": 2, "NP3-KEEPER": 1, "BASE3-03x10-T-aa77a9": 2,
    }, "B trial selection differs.")
    for row in trial:
        path = (ROOT / "kit/trial" / row["stl"]).resolve()
        require(path.is_relative_to(ROOT / "kit") and sha(path.read_bytes()) == row["sha256"],
                "Trial paths or hashes differ.")
    steps = read_csv(ROOT / "kit/B/steps.csv")
    require(len(steps) == len(assembly["steps"]) == 28 and sum(int(row["quantity"]) for row in steps) == 150,
            "Step counts differ.")
    require([identifier for step in assembly["steps"] for identifier in step["instances"]]
            == [row["id"] for row in assembly["placements"]], "Step instance order differs.")
    for step in steps:
        require((ROOT / "kit/B" / step["drawing"]).is_file(), "Step drawing missing.")
    sys.path.insert(0, str(ROOT / "source/scripts"))
    import design
    regenerated = design.build_catalog(design.load_parameters())
    for field in ("placements", "steps", "bom"):
        require(regenerated["models"][0][field] == assembly[field], f"Source layout differs: {field}")
    native = json.loads((ROOT / "verification/native.json").read_text())
    require(native["status"] == "PASS" and native["nameplate_lines"] == LINES, "Native verification missing.")
    for filename, digest in native["native_files_sha256"].items():
        require(sha((ROOT / filename).read_bytes()) == digest, "Native changed after verification.")
    pdf_text = subprocess.check_output(["pdftotext", str(ROOT / "kit/B/drawings.pdf"), "-"], text=True)
    require("github.com/tomokota" in pdf_text and "YOUR-USERNAME" not in pdf_text
            and pdf_text.count("\f") == 54, "Personal PDF content differs.")
    relative_links = verify_links(creating_report=args.write_report)
    privacy_scan()
    print_manifest = json.loads((ROOT / "kit/manifest.json").read_text())
    require(print_manifest["revision"] == REVISION and print_manifest["status"] == "NOT_SLICED" and print_manifest["sliced"] is False
            and print_manifest["pause_encoded"] is False and print_manifest["physical_tested"] is False,
            "Print package status differs.")
    require({row["file"] for row in print_manifest["files"]} == {
        path.relative_to(ROOT / "kit").as_posix() for path in (ROOT / "kit").rglob("*")
        if path.is_file() and path != ROOT / "kit/manifest.json"
    }, "Print manifest inventory differs.")
    for row in print_manifest["files"]:
        require(sha((ROOT / "kit" / row["file"]).read_bytes()) == row["sha256"], "Print manifest hash differs.")
    guide = print_manifest["offline_guide"]
    require(guide["entry"] == "guide/index.html" and guide["self_contained"] is True
            and guide["network_required"] is False and guide["server_required"] is False
            and guide["mapping"] == "guide/index.mapping.json" and guide["occurrence_csv"] == "kit/B/part-map.csv"
            and guide["assembly_placements"] == guide["plate_slots"] == 150,
            "Offline guide manifest contract differs.")
    guide_files = {path.relative_to(ROOT).as_posix() for path in (ROOT / "guide").rglob("*") if path.is_file()}
    require({row["file"] for row in guide["files"]} == guide_files, "Guide manifest inventory differs.")
    require(len(guide["files"]) == len(guide_files), "Guide manifest contains duplicate entries.")
    for row in guide["files"]:
        path = ROOT / row["file"]
        require(path.stat().st_size == row["bytes"] and sha(path.read_bytes()) == row["sha256"],
                "Offline guide manifest bytes or hash differ.")
    offline_document = verify_offline_html(ROOT / guide["entry"])
    guide_mapping = json.loads((ROOT / guide["mapping"]).read_text())
    guide_report = verify_mapping(guide_mapping)
    guide_report.update(verify_embedded(guide_mapping, ROOT / guide["entry"]))
    rows = read_csv(ROOT / guide["occurrence_csv"])
    slots = {slot["id"]: (plate, slot) for plate in guide_mapping["plates"] for slot in plate["slots"]}
    guide_placements = {row["id"]: row for row in guide_mapping["placements"]}
    require(len(rows) == len(slots) == 150
            and {f"{row['plate']}#{row['slot']}" for row in rows} == set(slots), "Slot CSV inventory differs.")
    for row in rows:
        plate, slot = slots[f"{row['plate']}#{row['slot']}"]
        placement = guide_placements[slot["suggested_placement"]]
        group = guide_mapping["groups"][slot["group"]]
        require(row["part"] == slot["part"] and row["color"] == plate["color"]
                and row["finish_color"] == guide_mapping["parts"][slot["part"]].get("finish_color", "")
                and row["suggested_placement"] == placement["id"] and int(row["suggested_step"]) == placement["step"]
                and row["candidate_placements"].split() == slot["candidate_placements"]
                and [int(step) for step in row["candidate_steps"].split()]
                == sorted({guide_placements[identifier]["step"] for identifier in slot["candidate_placements"]})
                and row["all_source_slots"].split() == [source["slot_id"] for source in group["sources"]],
                "Slot CSV mapping differs.")
        require(int(row["quantity_in_assembly"]) == group["quantity"]
                and int(row["quantity_on_plate"]) == sum(s["part"] == slot["part"] for s in plate["slots"])
                and [float(value) for value in row["dimensions_mm"].split(" x ")]
                == guide_mapping["parts"][slot["part"]]["dimensions"], "Slot CSV dimensions or counts differ.")
    for step in steps:
        members = [guide_placements[identifier] for identifier in step["placement_ids"].split()]
        require(step["source_slots"].split() == [row["suggested_source"]["slot_id"] for row in members]
                and step["parts"].split() == [row["part"] for row in members], "Step CSV source mapping differs.")
    browser_report = json.loads((ROOT / "verification/guide-browser.json").read_text())
    require(browser_report["status"] == "PASS" and browser_report["navigation_scheme"] == "file"
            and browser_report["browser_network_offline"] is True and browser_report["external_network_requests"] == 0
            and browser_report["console_or_page_errors"] == 0
            and browser_report.get("canonical_guide_sha256", browser_report["entry_sha256"])
            == canonical_guide_hash(ROOT / guide["entry"]),
            "Offline browser verification is missing or stale.")
    journal = json.loads((ROOT / "verification/build-log.json").read_text())
    require(journal["status"] in ("PASS", "PASS_DOCUMENTATION_STATIC")
            and journal["guide_entry_sha256"] == sha((ROOT / guide["entry"]).read_bytes())
            and journal["guide_base_sha256"] == canonical_guide_hash(ROOT / guide["entry"])
            and journal["photo_count"] == sum(batch["photo_count"] for batch in PHOTO_BATCHES)
            and journal["latest_progress_anchor"] == PROGRESS_ANCHOR
            and journal["all_image_files_decoded"] is True
            and journal["all_relative_image_paths_resolve"] is True
            and journal["browser_execution"] in ("PASS", "NOT_RUN_ENVIRONMENT"),
            "Current build-log navigation or image verification is missing.")
    for filename, expected_hash in journal["inputs_sha256"].items():
        require(sha((ROOT / filename).read_bytes()) == expected_hash,
                f"A verified build-log document or photo changed:{filename}")
    require(browser_report["checks"]["mapping_slots_checked"] == 150
            and browser_report["checks"]["mapping_placements_checked"] == 150
            and browser_report["checks"]["plate_ui_selections"] == 14
            and browser_report["checks"]["part_color_groups_ui_checked"] == 23
            and browser_report["checks"]["steps_navigated"] == 28, "Browser mapping/step coverage is incomplete.")
    require(browser_report["checks"]["step_7_replay_stops_at_24"] is True
            and browser_report["checks"]["step_7_replay_elapsed_seconds"] <= 15
            and browser_report["checks"]["play_button_matches_state"] is True,
            "Keeper-step playback timing/stop verification is incomplete.")
    require(set(browser_report["media_files"]) == {
        "docs/images/B-guide-start.png", "docs/images/B-guide-front.png", "docs/images/B-guide-base-front.gif",
    }, "Actual-render media inventory differs.")
    for filename, digest in browser_report["media_files"].items():
        require(sha((ROOT / filename).read_bytes()) == digest, "Guide render media differs from browser verification.")
    shared = json.loads((ROOT / "verification/guide-source-import.json").read_text())
    expected_shared = {
        "scripts/build_assembly_guide.py", "scripts/bundle_assembly_guide.mjs",
        "web/assembly-guide/model.js", "web/assembly-guide/viewer.js",
        "web/assembly-guide/template.html", "web/assembly-guide/style.css",
        "web/assembly-guide/runtime.js", "notices/THREE-LICENSE.txt",
    }
    require(shared["source_commit_verified"] is True
            and re.fullmatch(r"[0-9a-f]{40}", shared["source_commit"])
            and len(shared["files"]) == len(expected_shared)
            and {row["destination"] for row in shared["files"]} == expected_shared,
            "Shared guide provenance is incomplete or unpinned.")
    for row in shared["files"]:
        require(sha((ROOT / row["destination"]).read_bytes()) == row["sha256"],
                "Shared guide source/runtime differs from its pinned provenance.")
    verify_package()
    report = {
        "status": "PASS", "revision": REVISION, "model": "B", "units": "mm",
        "assembly_parts": 150, "B_unique_parts": 21, "B_bom_rows": 23, "B_plates": 14,
        "color_quantities": dict(Counter(row["color"] for row in assembly["placements"])),
        "steps": 28, "pdf_pages": 54, "trial_parts": 7, "fit_masters": 12,
        "separate_lettering_coupon": {"part": sample["part"], "quantity": 1, "included_in_assembly": False},
        "nameplate_lines": LINES, "native_reopen_report": "verification/native.json",
        "relative_links_checked": relative_links, "zip_duplicate_members": 0,
        "offline_guide": {"entry": guide["entry"], **offline_document, **guide_report,
                          "browser_report": "verification/guide-browser.json",
                          "common_source_commit": shared["source_commit"],
                          "common_ui_revision": shared["common_ui_revision"]},
        "build_record": {"report": "verification/build-log.json", "photo_count": journal["photo_count"],
                         "status": journal["status"], "browser_execution": journal["browser_execution"],
                         "formal_physical_validation": "NOT_PROVIDED"},
        "sliced": False, "pause_encoded": False, "physical_fit_strength_stability": "NOT_TESTED",
        "libraries": {"numpy": np.__version__, "trimesh": trimesh.__version__}, "meshes": mesh_reports,
    }
    if args.write_report:
        (ROOT / "verification/kit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print("Wrote verification/kit.json. Rebuild the ZIP/checksums, then verify again without --write-report.")
    print(f"PASS: 150 parts / 14 plates / 34 closed vertex-manifold STL masters / {relative_links} relative links / offline 3D + ZIP")


if __name__ == "__main__":
    main()
