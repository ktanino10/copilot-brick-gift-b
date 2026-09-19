"""B-only private part catalogue and placements. Coordinates and STL units are mm."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_parameters():
    parameters = json.loads((ROOT / "design/parameters.json").read_text())
    if [variant["id"] for variant in parameters["variants"]] != ["B"]:
        raise ValueError("This private kit contains only the approved B layout.")
    if parameters["message"]["lines"] != [
        "Same icon, New adventures", "github.com/tomokota"
    ]:
        raise ValueError("The private kit must retain its approved two display lines.")
    return parameters


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def brick_id(nx, ny, height):
    return f"BR-{nx:02d}x{ny:02d}-H{round(height * 10):03d}"


def cell(v, course, x):
    """Profile is discrete design data, not a scaled copy of another variant."""
    width = v["body_width"]
    goggle = v["goggle_bottom"]
    count = v["body_courses"]
    if course < goggle:
        inset = max(0, v["bottom_inset"] - course)
        if not inset <= x < width - inset:
            return None
        if course == 0:
            return ("magenta", *v["chin_y"])
        rim = 2
        if x < inset + rim or x >= width - inset - rim:
            return ("magenta", *v["headset_y"])
        color = "black"
        if v["eye_courses"][0] <= course <= v["eye_courses"][1]:
            if x in v["eye_columns"]:
                color = "green"
        return (color, *v["face_y"])
    inset = 2 if course == count - 1 else 1 if course == count - 2 else 0
    if not inset <= x < width - inset:
        return None
    if course in (goggle, count - 2, count - 1):
        return ("cyan", *v["goggle_y"])
    middle = width // 2
    is_frame = x < 2 or x >= width - 2 or middle - 1 <= x <= middle
    return ("cyan", *v["goggle_y"]) if is_frame else ("black", *v["face_y"])


def split_run(start, end, course):
    # Shift joints by two studs between courses; avoid a new one-stud cantilever.
    cursor = start
    first = 2 if course % 2 else 4
    while cursor < end:
        length = min(first if cursor == start else 4, end - cursor)
        if end - cursor - length == 1:
            length += 1
        yield cursor, length
        cursor += length


def build_catalog(p):
    pitch = p["interface"]["pitch"]
    height = p["interface"]["brick_height"]
    parts = {}
    models = []
    message = p["message"]

    def register(nx, ny, h):
        key = brick_id(nx, ny, h)
        parts[key] = {
            "id": key, "kind": "brick", "studs": [nx, ny], "height": h,
            "top_studs": True, "socket": True, "stl": f"parts/{key}.stl",
            "orientation": "underside_on_bed_studs_up",
        }
        return key

    parts["NP3-KEEPER"] = {
        "id": "NP3-KEEPER", "kind": "front_keeper", "studs": [2, 1], "height": 3.2,
        "top_studs": False, "socket": True, "socket_grid_offset": [0, 8],
        "stl": "parts/NP3-KEEPER.stl", "orientation": "flat_front_pad_and_socket_down",
    }
    for v in p["variants"]:
        placements = []
        steps = []

        def step(title):
            index = len(steps) + 1
            steps.append({"number": index, "title": title, "instances": []})
            return index

        def place(part, color, xyz, number, rotation=(0, 0, 0), **extra):
            instance = f'{v["id"]}-{len(placements) + 1:03d}'
            placements.append({
                "id": instance, "part": part, "color": color,
                "position": [round(n, 6) for n in xyz], "rotation": list(rotation),
                "step": number,
                **extra,
            })
            steps[number - 1]["instances"].append(instance)

        bw, bd = v["base_studs"]
        modules = [
            {"x": message["x"], "width": v["message_width"], "back_y": message["back_y"]},
            {"x": v["logo_x"], "width": v["logo_module_width"], "back_y": p["logo"]["back_y"]},
        ]
        for base_course in range(message["base_courses"]):
            number = step(f"黒い台座 {base_course + 1} / 5段目を積む（縦の継ぎ目をずらす）")
            segments = (v["base_segments_x"] if base_course == 0 else
                        ([6] * (bw // 6) if base_course % 2 else [3] + [6] * (bw // 6 - 1) + [3]))
            base_x = 0
            for segment in segments:
                slots = []
                segment_width = segment * pitch
                margin = message["side_taper"] + message["clearance"] + 1
                for module in modules:
                    left = module["x"] - base_x * pitch
                    right = left + module["width"]
                    if right < -margin or left > segment_width + margin:
                        continue
                    left, right = max(left, -margin), min(right, segment_width + margin)
                    slots.append({"x": round(left, 6), "width": round(right - left, 6),
                                  "back_y": module["back_y"]})
                geometry = {"studs": [segment, bd], "height": height, "slots": slots,
                            "bottom_course": base_course == 0}
                suffix = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:6]
                key = f"BASE3-{segment:02}x{bd:02}-{'B' if base_course == 0 else 'T'}-{suffix}"
                parts[key] = {
                    **geometry, "id": key, "kind": "front_base", "top_studs": True,
                    "socket": True, "reserved_rows": [0], "source_brick": brick_id(segment, bd, height),
                    "stl": f"parts/{key}.stl", "orientation": "underside_on_bed_studs_up",
                }
                place(key, "black", [base_x * pitch, 0, base_course * height], number,
                      role="base_course", course=base_course)
                base_x += segment
            if base_x != bw:
                raise ValueError("Every base course must exactly fill the nominal width")
        text_id, logo_id = f"NP3-TEXT-{v['id']}", f"NP3-LOGO-{v['id']}"
        parts[text_id] = {
            "id": text_id, "kind": "front_plaque", "width": v["message_width"],
            "text_sizes": v["text_sizes"], "text_heights": v["text_heights"], "text": message["lines"],
            "top_studs": False, "socket": False, "stl": f"parts/{text_id}.stl",
            "orientation": "flat_rear_on_bed_letters_up", "optional_color_change_z": message["thickness"],
            "letter_color": message["letter_color"],
        }
        parts[logo_id] = {
            "id": logo_id, "kind": "front_logo", "width": v["logo_module_width"],
            "diameter": v["logo_diameter"], "top_studs": False, "socket": False,
            "stl": f"parts/{logo_id}.stl", "orientation": "flat_rear_on_bed_relief_up",
            "optional_color_change_z": p["logo"]["finish_color_change_z"], "letter_color": "white",
        }
        number = step("大きい2行銘板と、その右隣のロゴを別々に前面の溝へ差し込む")
        place(text_id, "black", [message["x"], message["back_y"], message["bottom_z"]],
              number, (90, 0, 0), role="front_module", module="text")
        place(logo_id, "black", [v["logo_x"], p["logo"]["back_y"], message["bottom_z"]],
              number, (90, 0, 0), role="front_module", module="logo")
        number = step("銘板用2個・ロゴ用1個の黒いキーパーを2列目のスタッドに載せる")
        keeper_locations = [
            (0, "text"),
            (int((message["x"] + v["message_width"] - 16) // pitch) * pitch, "text"),
            (int((v["logo_x"] + v["logo_module_width"] / 2 - 8) // pitch) * pitch, "logo"),
        ]
        for x, module in keeper_locations:
            place("NP3-KEEPER", "black", [x, 0, message["base_courses"] * height], number,
                  role="keeper", module=module)
        offset_x = (bw - v["body_width"]) // 2
        for course in range(v["body_courses"]):
            number = step(f"本体 {course + 1} 段目を左から載せる")
            x = 0
            while x < v["body_width"]:
                spec = cell(v, course, x)
                end = x + 1
                while end < v["body_width"] and cell(v, course, end) == spec:
                    end += 1
                if spec is not None:
                    color, y0, y1 = spec
                    for start, length in split_run(x, end, course):
                        place(register(length, y1 - y0, height), color,
                              [(offset_x + start) * pitch, y0 * pitch,
                               (course + message["base_courses"]) * height], number, role="face")
                x = end
        number = step("頭頂のマゼンタのプレートを載せる")
        crest_start = (bw - v["crest_width"]) // 2
        for x, length in split_run(0, v["crest_width"], v["body_courses"]):
            place(register(length, v["face_y"][1] - v["face_y"][0],
                           v["crest_height"]), "magenta",
                  [(crest_start + x) * pitch, v["face_y"][0] * pitch,
                   (v["body_courses"] + message["base_courses"]) * height], number, role="face")
        step("2行と右ロゴが5段台座の正面内に収まること、保持と転倒を確認する")
        quantities = Counter((i["part"], i["color"]) for i in placements)
        bom = [{"part": key, "color": color, "quantity": n,
                "stl": parts[key]["stl"], "finish_color": parts[key].get("letter_color", ""),
                "color_change_z_mm": parts[key].get("optional_color_change_z", "")}
               for (key, color), n in sorted(quantities.items())]
        models.append({
            **v, "placements": placements, "steps": steps, "bom": bom,
            "presentation": p["presentation"],
            "base_courses": message["base_courses"], "base_body_height_mm": message["base_courses"] * height,
            "part_count": len(placements), "unique_prints": len({i["part"] for i in placements}),
        })
    for correction in p["fit_candidates"]["male_diameter_corrections"]:
        diameter = p["interface"]["reference_stud_diameter"] + correction
        key = f"FIT-M-D{round(diameter * 100):03d}"
        parts[key] = {
            "id": key, "kind": "male_coupon", "studs": [4, 2], "height": 3.2,
            "top_studs": True, "socket": False, "male_correction": correction,
            "stl": f"parts/{key}.stl", "orientation": "flat_bottom_studs_up",
        }
    for clearance in p["fit_candidates"]["female_radial_clearances"]:
        sign = "P" if clearance >= 0 else "M"
        key = f"FIT-F-C{sign}{round(abs(clearance) * 100):02d}"
        parts[key] = {
            "id": key, "kind": "female_coupon", "studs": [4, 2], "height": 9.6,
            "top_studs": False, "socket": True, "female_clearance": clearance,
            "stl": f"parts/{key}.stl", "orientation": "socket_down",
        }
    parts["NP3-FIT-PLAQUE"] = {
        "id": "NP3-FIT-PLAQUE", "kind": "front_fit_plaque", "width": 24,
        "top_studs": False, "socket": False, "stl": "parts/NP3-FIT-PLAQUE.stl",
        "orientation": "flat_rear_on_bed",
    }
    for clearance in (.15, .20, .25):
        key = f"NP3-FIT-SOCKET-C{round(clearance * 100):02}"
        parts[key] = {
            "id": key, "kind": "front_fit_socket", "studs": [4, 2], "height": 9.6,
            "bottom_course": True, "reserved_rows": [0],
            "slots": [{"width": 24, "x": 4, "clearance": clearance,
                       "back_y": message["back_y"], "bottom_z": .2}],
            "top_studs": True, "socket": True, "stl": f"parts/{key}.stl",
            "orientation": "underside_on_bed_studs_up",
        }
    return {
        "schema_version": 1, "revision": p["revision"], "units": "mm",
        "publication": {"mode": "private", "public_text_approved": False},
        "parameters_sha256": digest(ROOT / "design/parameters.json"),
        "interface": p["interface"], "message": p["message"], "logo": p["logo"], "colors": p["colors"],
        "parts": parts, "models": models,
    }


def interface_contract(p):
    return {
        "id": "BASE-FRONT-NP3", "revision": p["revision"], "units": "mm",
        "status": p["status"], "brick": p["interface"], "message": p["message"], "logo": p["logo"],
        "variants": [{key: v[key] for key in ("id", "message_width", "logo_x", "logo_module_width", "logo_diameter")}
                     for v in p["variants"]],
        "note": "Design candidates, not a LEGO specification or compatibility certification.",
        "insertion": "Independent downward dovetail slides into the five-course base front; 2 text keepers and 1 logo keeper prevent upward escape.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory outside the shipped source files; does not build meshes.")
    args = parser.parse_args()
    p = load_parameters()
    catalog = build_catalog(p)
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError("Choose a new output directory outside source/; shipped inputs are not overwritten.")
    write_json(output / "catalog.json", catalog)
    write_json(output / "interface.json", interface_contract(p))
    for model in catalog["models"]:
        print(model["id"], model["part_count"], "parts,", len(model["steps"]), "steps")


if __name__ == "__main__":
    main()
