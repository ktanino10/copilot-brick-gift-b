#!/usr/bin/env python3
"""Build B-only indexes, guide inventory and one deterministic offline kit archive."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import zipfile

from verify_guide_mapping import verify_mapping


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "downloads/B-personal-print-kit.zip"
DELIVERY_DIRS = ("docs", "guide", "kit", "samples", "source", "web", "notices", "scripts", "verification")
DELIVERY_FILES = (
    ".gitattributes", ".gitignore", "README.md", "requirements-verify.txt", "requirements-guide.txt", "requirements-cad.txt",
    "package.json", "package-lock.json",
)
REVISION = "4.1-B-legibility.1"
COLORS = {"black": "黒", "cyan": "シアン", "magenta": "マゼンタ", "green": "緑"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_files():
    paths = [ROOT / name for name in DELIVERY_FILES]
    for folder in DELIVERY_DIRS:
        paths.extend(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix not in (".pyc", ".FCBak", ".FCStd1"))
    return sorted(paths)


def mapping_rows(mapping):
    placements = {item["id"]: item for item in mapping["placements"]}
    rows = []
    for plate in mapping["plates"]:
        counts = Counter(slot["part"] for slot in plate["slots"])
        for slot in plate["slots"]:
            part = mapping["parts"][slot["part"]]
            group = mapping["groups"][slot["group"]]
            assigned = placements[slot["suggested_placement"]]
            rows.append({
                "plate": plate["file"], "slot": slot["number"], "part": slot["part"],
                "color": plate["color"], "finish_color": part.get("finish_color", ""),
                "dimensions_mm": " x ".join(f"{size:g}" for size in part["dimensions"]),
                "quantity_on_plate": counts[slot["part"]], "quantity_in_assembly": group["quantity"],
                "suggested_placement": assigned["id"], "suggested_step": assigned["step"],
                "candidate_placements": " ".join(slot["candidate_placements"]),
                "candidate_steps": " ".join(str(step) for step in sorted({
                    placements[identifier]["step"] for identifier in slot["candidate_placements"]
                })),
                "all_source_slots": " ".join(source["slot_id"] for source in group["sources"]),
            })
    return rows


def plate_anchor(filename):
    return filename.lower().replace(".", "")


def write_indexes():
    if not (ROOT / "guide/index.html").is_file():
        raise ValueError("Build the standalone guide/index.html before packaging the print kit.")
    assembly = json.loads((ROOT / "kit/B/assembly.json").read_text())
    manifest = json.loads((ROOT / "kit/B/plates/manifest.json").read_text())
    mapping = json.loads((ROOT / "guide/index.mapping.json").read_text())
    verify_mapping(mapping)
    mapped_placements = {item["id"]: item for item in mapping["placements"]}
    occurrences = mapping_rows(mapping)
    with (ROOT / "kit/B/part-map.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(occurrences[0]))
        writer.writeheader()
        writer.writerows(occurrences)
    with (ROOT / "kit/B/bom.csv").open(newline="") as stream:
        bom = list(csv.DictReader(stream))
    if assembly["model"] != "B" or len(assembly["placements"]) != 150:
        raise ValueError("Only the approved 150-part B assembly can be packaged.")
    steps = []
    for step in assembly["steps"]:
        ids = step["instances"]
        steps.append({
            "step": step["number"], "title": step["title"], "quantity": len(ids),
            "placement_ids": " ".join(ids), "drawing": f"drawings/step-{step['number']:02}.svg",
            "source_slots": " ".join(mapped_placements[identifier]["suggested_source"]["slot_id"] for identifier in ids),
            "parts": " ".join(mapped_placements[identifier]["part"] for identifier in ids),
        })
    with (ROOT / "kit/B/steps.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(steps[0]))
        writer.writeheader()
        writer.writerows(steps)
    step_lines = [
        "# Bの28工程", "", "[入口](../README.md) · [オフライン3D](../guide/index.html) · "
        "[3Dの使い方](GUIDE.md) · [組立・交換・分解](ASSEMBLY.md) · "
        "[全図PDF](../kit/B/drawings.pdf)", "",
        "**現行の銘板は上12／下10 mm・白1.2 mmの改訂版。"
        "[文字試験片](NAMEPLATE-V2.md)は完成150個とは別です。**", "",
        "**ZIPを展開して `guide/index.html` をダブルクリック。空の机から全28工程を3Dで進められます。**",
        "Python／Node／ネット接続は閲覧に不要です。印刷順と組立順は別です。",
        "**工程1は `B-black-02.3mf` のslot 3、`BASE3-24x10-B-562406` → `B-001`。**",
        "black-01の8個は2〜5段目用です。台座5段の出処はblack-01〜04にまたがります。",
        "slot番号は案内用で刻印なし。同一ID・色の実物は可換で、特定個体の割当ではありません。",
        "",
        "図の下が手前（銘板側）です。追加する配置番号を、その工程の図で確認します。",
        "最終工程は確認だけで、新しい部品はありません。図は実CAD由来で、実物の合格証拠ではありません。",
        "", "[全150slotの対応CSV](../kit/B/part-map.csv) · [全14枚の部品・寸法表](FILES.md)",
        "", "| 工程図 | 内容 | 追加数 | 配置番号 | 3MFの便宜出処 |", "|---|---|---:|---|---|",
    ]
    for row in steps:
        ids = row["placement_ids"].split()
        label = (f"`{ids[0]}`〜`{ids[-1]}`" if len(ids) > 1 else f"`{ids[0]}`") if ids else "追加なし"
        files = sorted({mapped_placements[identifier]["suggested_source"]["plate"] for identifier in ids})
        source_label = "、".join(f"`{file}`" for file in files) or "追加なし"
        step_lines.append(
            f"| [{row['step']:02}](../kit/B/{row['drawing']}) | {row['title']} | "
            f"{row['quantity']} | {label} | {source_label} |"
        )
    step_lines += [
        "", "工程1〜5は台座、6は前面2部品、7はkeeper、8〜26は顔19段、27は頭頂、28は確認です。",
        "試作の端部2個だけを積む操作を、正式な5段配置と取り違えないでください。",
        "", "![実形状による空の机から台座・前面・keeperへの短い組立アニメーション]"
        "(images/B-guide-base-front.gif)",
        "",
        "最初の1枚はblack-02 slot 3。前面はblack-to-white-z2p4／z2p8の各slot 1、"
        "keeperはblack-07 slot 8〜10です。持ち上げ・透過・分解表示は説明用で、物理的な経路保証ではありません。",
        "", "## 前面の取り付け図", "",
        "![前面2部品の取り付け位置](../kit/B/drawings/step-06.svg)", "",
        "![keeper3個の配置](../kit/B/drawings/step-07.svg)", "",
        "## 1個ごとの取り出し表", "",
        "以下は3MFの元の順番に対応させた便宜割当です。同一ID・同一色なら別slotの良品を使えます。",
        "実物への刻印ではありません。試作から流用した分もここへ引き当て、再印刷を重複させません。", "",
    ]
    for step in mapping["steps"]:
        step_lines += [
            f"### 工程{step['number']}：{step['title']}", "",
        ]
        if not step["instances"]:
            step_lines += ["追加0個。150個がそろったら実物の保持・着座・安定を確認します。", ""]
            continue
        step_lines += [
            "| 配置番号 | 部品ID | 3MF | slot | 印刷姿勢の外形 mm |",
            "|---|---|---|---:|---|",
        ]
        for identifier in step["instances"]:
            item = mapped_placements[identifier]
            source = item["suggested_source"]
            dimensions = " × ".join(f"{size:g}" for size in mapping["parts"][item["part"]]["dimensions"])
            step_lines.append(
                f"| `{identifier}` | [{item['part']}](../kit/B/parts/{item['part']}.stl) | "
                f"[{source['plate']}](../kit/B/plates/{source['plate']}) | {source['slot']} | {dimensions} |"
            )
        step_lines.append("")
    (ROOT / "docs/STEPS.md").write_text("\n".join(step_lines))

    file_lines = [
        "# Bのファイル一覧と数量", "",
        "[入口](../README.md) · [オフライン3D](../guide/index.html) · [3Dの使い方](GUIDE.md) · "
        "[印刷手順](PRINTING.md) · [少量試作](TRIAL.md)", "",
        "**2026-09-22の変更は文字銘板1枚だけです。全厚3.6 mm・上12／下10 mm・白1.2 mm。"
        "まず[小さな文字試験片](NAMEPLATE-V2.md)から。台座・顔・右ロゴは刷り直し不要です。**", "",
        "**印刷したファイルから探す：ZIPを展開して `guide/index.html` をダブルクリックし、"
        "3MFとslotを選びます。実プレートの配置と完成／途中の対応位置が3Dで見られます。**",
        "全14枚／150配置を照合しています。slotは案内用の番号で、実物には刻印されていません。",
        "同じ部品ID・色は可換です。便宜上の割当を実物の固有番号とは扱いません。",
        "**色表とblack-01からの印刷順は組立順ではありません。1段目はblack-02 slot 3のB-001です。**", "",
        "**全ファイルNOT_SLICED。STLと3MFは代替です。同じ部品の両形式を読み込まないでください。**",
        "この一覧はBOM・3MF manifestから生成しています。各プレートを空のプロジェクトへ1枚ずつ開きます。",
        "3MFにはPause、検証済みプリンタ設定、G-codeがありません。個人銘板は既に置換済みです。",
        "", "## 配置済み3MF：全14枚、計150個", "",
        "| ファイル | 色・用途 | 配置個数 | slotと組立位置 |", "|---|---|---:|---|",
    ]
    plates = sorted(manifest["plates"], key=lambda row: (
        4 if row["finish_color"] else list(COLORS).index(row["color"]),
        float(row["manual_change_after_z_mm"] or 0), row["file"],
    ))
    for plate in plates:
        color = COLORS[plate["color"]]
        if plate["finish_color"]:
            color += "→白・" + ("個人銘板（2.4 mm後）" if plate["manual_change_after_z_mm"] == 2.4 else "右ロゴ（2.8 mm後）")
        file_lines.append(
            f"| [{plate['file']}](../kit/B/plates/{plate['file']}) | {color} | {len(plate['items'])} | "
            f"[対応表](#{plate_anchor(plate['file'])}) |"
        )
    file_lines += [
        "", "色替えの高さは目安となる境界です。実レイヤープレビューで黒地終了後／最初の白path前へPauseを入れ、",
        "停止・交換・再開を本人が確認してください。固定層番号には変換しません。",
        "", "## 手配置用STL：21形状、色別23行、完成150個", "",
        "1つのSTLファイルは形状1種類です。以下の色ごとの数量が必要数です。",
        "試作から完成品へ流用する良品があれば、既印刷数として引き当てて重複印刷を避けます。",
        "", "| STL／部品ID | 色 | 完成必要数 |", "|---|---|---:|",
    ]
    for row in bom:
        color = COLORS[row["color"]] + ("→白" if row["finish_color"] else "")
        file_lines.append(f"| [{row['part']}](../kit/B/{row['stl']}) | {color} | {row['quantity']} |")
    file_lines += [
        "", "## 全数印刷より先に使うもの", "",
        "まず [FIT-M-D470](../kit/fit/FIT-M-D470.stl)＋[FIT-F-CP12](../kit/fit/FIT-F-CP12.stl)を各1個。",
        "キー溝は [NP3-FIT-PLAQUE](../kit/fit/NP3-FIT-PLAQUE.stl)＋"
        "[NP3-FIT-SOCKET-C25](../kit/fit/NP3-FIT-SOCKET-C25.stl)から必要分だけ。",
        "", "他のfit候補は [kit/fit/](../kit/fit/)にありますが、全種類を一括印刷しません。",
        "候補は合格補正値ではありません。次の[試作BOM](../kit/trial/bom.csv)はBの7個だけです。",
        "", "| 実部品の試作 | 個数 |", "|---|---:|",
        "| [BR-02x02-H096](../kit/trial/parts/BR-02x02-H096.stl) | 2 |",
        "| [BR-02x04-H096](../kit/B/parts/BR-02x04-H096.stl) | 2 |",
        "| [NP3-KEEPER](../kit/B/parts/NP3-KEEPER.stl) | 1 |",
        "| [BASE3-03x10-T-aa77a9](../kit/B/parts/BASE3-03x10-T-aa77a9.stl) | 2（同じ左端形状） |",
        "", "4個→3個と段階を分けます。2×2は完成BOMにない共通接続の試験用で、完成150個には数えません。",
        "", "## 各3MFのslot・形状・寸法・適用先：全150項目", "",
        "[対応CSV](../kit/B/part-map.csv) · [検査用mapping JSON](../guide/index.mapping.json) · "
        "[実プレートを3Dで見る](../guide/index.html)", "",
        "slotは元3MFの順番です。各行は印刷配置1個で、同形の行でも別の印刷配置を数えています。",
        "「同形数」はこのプレート内／完成B全体の同ID・同色数。「全適用先」は可換な全候補で、"
        "各行の実物を候補全部へ同時に使う意味ではありません。",
        "便宜割当は150個を過不足なく数える案内です。寸法は印刷姿勢のスタッド・レリーフ込み外形です。", "",
    ]
    for plate in plates:
        file_lines += [
            f"### {plate['file']}", "",
            "[3Dガイド](../guide/index.html)でこのファイルを選び、同じslot番号の実形状を確認します。", "",
            "| slot | 部品ID | 外形 W×D×H mm | 同形数（板内／全体） | 便宜割当／工程 | 全適用先 | 適用工程 |",
            "|---:|---|---|---:|---|---|---|",
        ]
        for row in occurrences:
            if row["plate"] != plate["file"]:
                continue
            ids = "、".join(f"`{identifier}`" for identifier in row["candidate_placements"].split())
            dimensions = row["dimensions_mm"].replace(" x ", " × ")
            file_lines.append(
                f"| {row['slot']} | [{row['part']}](../kit/B/parts/{row['part']}.stl) | {dimensions} | "
                f"{row['quantity_on_plate']}／{row['quantity_in_assembly']} | "
                f"`{row['suggested_placement']}`／{row['suggested_step']} | {ids} | "
                f"{'、'.join(row['candidate_steps'].split())} |"
            )
        file_lines.append("")
    file_lines += [
        "", "## 保管・照合", "",
        "[BOM](../kit/B/bom.csv) · [slot対応CSV](../kit/B/part-map.csv) · "
        "[工程CSV](../kit/B/steps.csv) · [組立配置](../kit/B/assembly.json) · "
        "[全図PDF](../kit/B/drawings.pdf) · [印刷ファイルmanifest](../kit/manifest.json)",
        "", "[完成FreeCAD](../source/native/B.FCStd) · [銘板FreeCAD](../source/native/NP3-TEXT-B.FCStd) · "
        "[銘板STEP](../source/native/NP3-TEXT-B.step)",
        "", "[全キットZIP](https://github.com/ktanino10/copilot-brick-gift-b/blob/main/downloads/B-personal-print-kit.zip) · "
        "[ファイルSHA-256](../SHA256SUMS.txt) · "
        "[ZIPのSHA-256](https://github.com/ktanino10/copilot-brick-gift-b/blob/main/downloads/SHA256SUMS.txt)", "",
    ]
    (ROOT / "docs/FILES.md").write_text("\n".join(file_lines))
    kit_manifest = {
        "revision": REVISION, "visibility": "private",
        "model": "B", "units": "mm", "status": "NOT_SLICED", "sliced": False,
        "printer_settings_validated": False, "pause_encoded": False, "physical_tested": False,
        "physical_tested_scope": "Formal fit, retention, load and stability validation is not provided; see separate photographic observations.",
        "assembly_dimensions_mm": [191.8, 80.2, 238.6], "assembly_quantity": 150,
        "base_color_quantities": dict(Counter(row["color"] for row in assembly["placements"])),
        "unique_assembly_stl": 21, "assembly_bom_rows": 23, "plates": 14,
        "trial_quantity_separate_from_assembly": 7, "fit_master_count": 12,
        "nameplate": manifest["nameplate"],
        "build_record": {
            "markdown": "docs/BUILD-LOG.md", "offline_html": "docs/BUILD-LOG.html",
            "photo_manifest": "docs/images/build-log-2026-09-23/manifest.json",
            "reported_through": "2026-09-23", "photo_count": 9,
            "observed_milestone": "nameplate trial and base/front-module assembly",
            "formal_physical_validation": "NOT_PROVIDED",
            "full_model_completion": "NOT_CONFIRMED",
            "photo_input_revision_hash_match": "NOT_CONFIRMED",
        },
        "lettering_sample": {
            "manifest": "samples/nameplate-v2/manifest.json", "quantity": 1,
            "included_in_assembly_bom": False, "dimensions_mm": [65.4, 30.9, 3.6],
            "files": [
                {"file": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
                for path in sorted((ROOT / "samples/nameplate-v2").iterdir()) if path.is_file()
            ],
        },
        "offline_guide": {
            "entry": "guide/index.html", "self_contained": True,
            "mapping": "guide/index.mapping.json", "occurrence_csv": "kit/B/part-map.csv",
            "network_required": False, "server_required": False, "webgl_required": True,
            "assembly_placements": 150, "plate_slots": 150,
            "files": [
                {"file": path.relative_to(ROOT).as_posix(),
                 "bytes": path.stat().st_size, "sha256": sha(path)}
                for path in sorted((ROOT / "guide").rglob("*")) if path.is_file()
            ],
        },
        "files": [
            {"file": str(path.relative_to(ROOT / "kit")), "bytes": path.stat().st_size, "sha256": sha(path)}
            for path in sorted((ROOT / "kit").rglob("*"))
            if path.is_file() and path != ROOT / "kit/manifest.json"
        ],
    }
    (ROOT / "kit/manifest.json").write_text(json.dumps(kit_manifest, ensure_ascii=False, indent=2) + "\n")


def main():
    write_indexes()
    files = payload_files()
    checksums = ROOT / "SHA256SUMS.txt"
    checksums.write_text("".join(f"{sha(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in files))
    files.append(checksums)
    ARCHIVE.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            name = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    (ARCHIVE.parent / "SHA256SUMS.txt").write_text(f"{sha(ARCHIVE)}  {ARCHIVE.name}\n")
    print(f"{ARCHIVE.relative_to(ROOT)}: {ARCHIVE.stat().st_size} bytes; {len(files)} unique members")


if __name__ == "__main__":
    main()
