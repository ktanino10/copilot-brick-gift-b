#!/usr/bin/env python3
"""Independently verify every private B slot, placement and embedded STL."""

import argparse
import base64
from collections import Counter, defaultdict
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "catalog": "source/design/catalog.json",
    "assembly": "kit/B/assembly.json",
    "plates": "kit/B/plates/manifest.json",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_mapping(mapping, root=ROOT):
    inputs = {key: read_json(root / name) for key, name in INPUTS.items()}
    assembly, manifest, catalog = inputs["assembly"], inputs["plates"], inputs["catalog"]
    require(mapping["schema_version"] == 1 and mapping["model"] == "B"
            and mapping["units"] == "mm" and mapping["part_count"] == 150, "Wrong B guide scope.")
    require(mapping["sliced"] is False and mapping["physical_fit_tested"] is False
            and mapping["slot_numbers_are_physical_markings"] is False, "Wrong guide safety status.")
    require(mapping["inputs_sha256"] == {key: sha((root / name).read_bytes()) for key, name in INPUTS.items()},
            "Guide inputs changed; rebuild the guide from the current approved inputs.")
    require(mapping["geometry_revision"] == catalog["revision"] and mapping["bounds"] == assembly["bounds"],
            "Guide geometry revision or assembled bounds differ.")
    require(mapping["colors"] == {
        key: {"hex": value["hex"], "name": value.get("name_ja", key)}
        for key, value in catalog["colors"].items()
    }, "Guide palette differs.")
    placements = {row["id"]: row for row in assembly["placements"]}
    require(len(placements) == 150, "Source assembly has duplicate or missing placements.")
    candidates = defaultdict(list)
    for row in assembly["placements"]:
        candidates[row["part"] + "|" + row["color"]].append(row["id"])
    require(set(mapping["groups"]) == set(candidates), "Guide part/color groups differ.")
    require(set(mapping["parts"]) == {row["part"] for row in placements.values()}, "Guide master set differs.")
    for part_id, part in mapping["parts"].items():
        original = catalog["parts"][part_id]
        for field in ("id", "kind", "bounds", "sha256", "orientation"):
            require(part[field] == original[field], f"Guide part {field} differs: {part_id}")
        require(part["dimensions"] == [round(hi - lo, 4) for lo, hi in zip(*original["bounds"])],
                f"Guide print dimensions differ: {part_id}")
        require(part["sha256"] == sha((root / "kit/B" / original["stl"]).read_bytes()),
                f"Actual STL hash differs: {part_id}")
        if part_id in {"NP3-TEXT-B", "NP3-LOGO-B"}:
            expected_height = 2.4 if part_id == "NP3-TEXT-B" else 2.8
            require(part["finish_color"] == "white" and part["color_change_z_mm"] == expected_height,
                    f"Front relief color boundary differs: {part_id}")
        else:
            require("finish_color" not in part and "color_change_z_mm" not in part,
                    f"Unexpected body color change: {part_id}")
    require(len(mapping["plates"]) == len(manifest["plates"]) == 14, "Guide must cover all 14 plates.")
    sources, used, assigned = defaultdict(list), Counter(), {}
    for plate, original in zip(mapping["plates"], manifest["plates"]):
        require(plate["file"] == original["file"] and plate["color"] == original["color"],
                "Guide plate order or color differs.")
        require(plate["sha256"] == sha((root / "kit/B/plates" / plate["file"]).read_bytes()),
                "Actual 3MF bytes changed after guide generation.")
        require(len(plate["slots"]) == len(original["items"]), "Guide plate occurrence count differs.")
        require(plate.get("finish_color", "") == original.get("finish_color", ""),
                "Guide plate finish color differs.")
        if original.get("finish_color"):
            require(plate["manual_change_after_z_mm"] == original["manual_change_after_z_mm"],
                    "Guide plate color-change height differs.")
        for number, (slot, item) in enumerate(zip(plate["slots"], original["items"]), 1):
            group = item["part"] + "|" + original["color"]
            require(slot["id"] == f"{plate['file']}#{number}" and slot["number"] == number
                    and slot["part"] == item["part"] and slot["group"] == group,
                    "Guide slot identity differs from real 3MF order.")
            require(slot["print_position"] == item["position"] and slot["print_rotation"] == [0, 0, 0]
                    and slot["brim_box"] == item["brim_box"], "Guide print transform differs.")
            require(slot["candidate_placements"] == candidates[group],
                    "Guide slot is missing or inventing an interchangeable placement.")
            identifier = candidates[group][used[group]]
            used[group] += 1
            require(slot["suggested_placement"] == identifier, "Guide-only assignment is not stable.")
            source = {"plate": plate["file"], "slot": number, "slot_id": slot["id"],
                      "suggested_placement": identifier}
            sources[group].append(source)
            require(identifier not in assigned, "A guide occurrence is assigned twice.")
            assigned[identifier] = source
    require(set(assigned) == set(placements), "A printed occurrence or assembly position is missing.")
    for group, ids in candidates.items():
        part, color = group.split("|")
        require(mapping["groups"][group] == {
            "part": part, "color": color, "placements": ids, "sources": sources[group], "quantity": len(ids),
        }, "The reverse part/color source map differs.")
    require(len(mapping["placements"]) == 150, "Guide assembly placement count differs.")
    for index, (row, original) in enumerate(zip(mapping["placements"], assembly["placements"])):
        require(all(row[key] == value for key, value in original.items()), "Guide assembly transform or role differs.")
        require(row["index"] == index and row["group"] == original["part"] + "|" + original["color"]
                and row["suggested_source"] == assigned[original["id"]], "Guide placement reverse source differs.")
    require(len(mapping["steps"]) == len(assembly["steps"]) == 28, "Guide step count differs.")
    cursor = 0
    for step, original in zip(mapping["steps"], assembly["steps"]):
        require(all(step[key] == value for key, value in original.items()), "Guide step content differs.")
        require(step["first_index"] == cursor and step["end_index"] == cursor + len(original["instances"]),
                "Guide step boundaries would omit or duplicate placements.")
        cursor += len(original["instances"])
        available = sorted({source["plate"] for identifier in original["instances"]
                            for source in sources[placements[identifier]["part"] + "|" + placements[identifier]["color"]]})
        require(step["available_source_files"] == available, "Guide step sources are incomplete.")
    require(cursor == 150, "Guide steps do not account for all 150 parts.")
    require(mapping["first_source"] == {
        "plate": "B-black-02.3mf", "slot": 3, "slot_id": "B-black-02.3mf#3", "suggested_placement": "B-001",
    }, "The beginner's first base must be black-02 slot 3 / B-001.")
    require(mapping["base_source_files"] == [f"B-black-{number:02}.3mf" for number in range(1, 5)],
            "The five-course base needs black-01 through black-04.")
    require(assigned["B-016"]["slot_id"] == "B-black-04.3mf#1"
            and assigned["B-017"]["slot_id"] == "B-black-04.3mf#2", "Fifth-course central source differs.")
    require(placements["B-020"]["rotation"] == placements["B-021"]["rotation"] == [90, 0, 0],
            "Front modules must use the assembled 90-degree orientation.")
    return {"plates": 14, "slots": 150, "placements": 150, "steps": 28,
            "bidirectional_groups": len(candidates), "stl_masters": len(mapping["parts"])}


class EmbeddedData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.count = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("id") == "assembly-guide-data":
            require(attrs.get("type") == "application/json", "Guide data script has the wrong type.")
            self.inside = True
            self.count += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, text):
        if self.inside:
            self.chunks.append(text)


def verify_embedded(mapping, entry, root=ROOT):
    parser = EmbeddedData()
    parser.feed(entry.read_text(encoding="utf-8"))
    parser.close()
    require(parser.count == 1, "Expected exactly one embedded guide dataset.")
    embedded = json.loads("".join(parser.chunks))
    require(embedded["mapping"] == mapping, "Embedded mapping differs from its inspectable JSON sidecar.")
    require(set(embedded["meshes"]) == set(mapping["parts"]), "Embedded mesh master set differs.")
    triangles = 0
    for part, mesh in embedded["meshes"].items():
        require(mesh["encoding"] == "gzip-base64-stl", "Unexpected embedded mesh encoding.")
        actual = gzip.decompress(base64.b64decode(mesh["payload"], validate=True))
        source = (root / "kit/B/parts" / f"{part}.stl").read_bytes()
        require(actual == source and sha(actual) == mesh["sha256"] == mapping["parts"][part]["sha256"],
                "Embedded geometry differs from the actual print STL.")
        count = struct.unpack_from("<I", actual, 80)[0]
        require(len(actual) == mesh["bytes"] == 84 + 50 * count and count == mesh["triangles"],
                "Embedded mesh byte or triangle count differs.")
        triangles += count
    return {"embedded_meshes": len(embedded["meshes"]), "embedded_triangles": triangles,
            "embedded_stl_byte_identical": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-only", action="store_true")
    args = parser.parse_args()
    mapping = read_json(ROOT / "guide/index.mapping.json")
    report = verify_mapping(mapping)
    if not args.mapping_only:
        report.update(verify_embedded(mapping, ROOT / "guide/index.html"))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
