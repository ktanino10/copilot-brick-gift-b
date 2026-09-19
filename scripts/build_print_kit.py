#!/usr/bin/env python3
"""Build B-only indexes, checksums and one deterministic offline kit archive."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "downloads/B-personal-print-kit.zip"
DELIVERY_DIRS = ("docs", "kit", "source", "notices", "scripts", "verification")
DELIVERY_FILES = (".gitattributes", ".gitignore", "README.md", "requirements-verify.txt")
COLORS = {"black": "黒", "cyan": "シアン", "magenta": "マゼンタ", "green": "緑"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_files():
    paths = [ROOT / name for name in DELIVERY_FILES]
    for folder in DELIVERY_DIRS:
        paths.extend(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix != ".pyc")
    return sorted(paths)


def write_indexes():
    assembly = json.loads((ROOT / "kit/B/assembly.json").read_text())
    manifest = json.loads((ROOT / "kit/B/plates/manifest.json").read_text())
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
        })
    with (ROOT / "kit/B/steps.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(steps[0]))
        writer.writeheader()
        writer.writerows(steps)
    step_lines = [
        "# Bの28工程", "", "[入口](../README.md) · [組立・交換・分解](ASSEMBLY.md) · "
        "[全図PDF](../kit/B/drawings.pdf)", "",
        "図の下が手前（銘板側）です。追加する配置番号を、その工程の図で確認します。",
        "最終工程は確認だけで、新しい部品はありません。図は実CAD由来で、実物の合格証拠ではありません。",
        "", "| 工程図 | 内容 | 追加数 | 配置番号 |", "|---|---|---:|---|",
    ]
    for row in steps:
        ids = row["placement_ids"].split()
        label = (f"`{ids[0]}`〜`{ids[-1]}`" if len(ids) > 1 else f"`{ids[0]}`") if ids else "追加なし"
        step_lines.append(f"| [{row['step']:02}](../kit/B/{row['drawing']}) | {row['title']} | {row['quantity']} | {label} |")
    step_lines += [
        "", "工程1〜5は台座、6は前面2部品、7はkeeper、8〜26は顔19段、27は頭頂、28は確認です。",
        "試作の端部2個だけを積む操作を、正式な5段配置と取り違えないでください。",
        "", "## 前面の取り付け図", "",
        "![前面2部品の取り付け位置](../kit/B/drawings/step-06.svg)", "",
        "![keeper3個の配置](../kit/B/drawings/step-07.svg)", "",
    ]
    (ROOT / "docs/STEPS.md").write_text("\n".join(step_lines))

    file_lines = [
        "# Bのファイル一覧と数量", "",
        "[入口](../README.md) · [印刷手順](PRINTING.md) · [少量試作](TRIAL.md)", "",
        "**全ファイルNOT_SLICED。STLと3MFは代替です。同じ部品の両形式を読み込まないでください。**",
        "この一覧はBOM・3MF manifestから生成しています。各プレートを空のプロジェクトへ1枚ずつ開きます。",
        "3MFにはPause、検証済みプリンタ設定、G-codeがありません。個人銘板は既に置換済みです。",
        "", "## 配置済み3MF：全14枚、計150個", "",
        "| ファイル | 色・用途 | 配置個数 |", "|---|---|---:|",
    ]
    plates = sorted(manifest["plates"], key=lambda row: (
        4 if row["finish_color"] else list(COLORS).index(row["color"]),
        float(row["manual_change_after_z_mm"] or 0), row["file"],
    ))
    for plate in plates:
        color = COLORS[plate["color"]]
        if plate["finish_color"]:
            color += "→白・" + ("個人銘板（2.4 mm後）" if plate["manual_change_after_z_mm"] == 2.4 else "右ロゴ（2.8 mm後）")
        file_lines.append(f"| [{plate['file']}](../kit/B/plates/{plate['file']}) | {color} | {len(plate['items'])} |")
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
        "", "## 保管・照合", "",
        "[BOM](../kit/B/bom.csv) · [工程CSV](../kit/B/steps.csv) · [組立配置](../kit/B/assembly.json) · "
        "[全図PDF](../kit/B/drawings.pdf) · [印刷ファイルmanifest](../kit/manifest.json)",
        "", "[完成FreeCAD](../source/native/B.FCStd) · [銘板FreeCAD](../source/native/NP3-TEXT-B.FCStd) · "
        "[銘板STEP](../source/native/NP3-TEXT-B.step)",
        "", "[全キットZIP](https://github.com/ktanino10/copilot-brick-gift-b/blob/main/downloads/B-personal-print-kit.zip) · "
        "[ファイルSHA-256](../SHA256SUMS.txt) · "
        "[ZIPのSHA-256](https://github.com/ktanino10/copilot-brick-gift-b/blob/main/downloads/SHA256SUMS.txt)", "",
    ]
    (ROOT / "docs/FILES.md").write_text("\n".join(file_lines))
    kit_manifest = {
        "revision": "4.0-B-personal-kit.1", "visibility": "private",
        "model": "B", "units": "mm", "status": "NOT_SLICED", "sliced": False,
        "printer_settings_validated": False, "pause_encoded": False, "physical_tested": False,
        "assembly_dimensions_mm": [191.8, 79.8, 238.6], "assembly_quantity": 150,
        "base_color_quantities": dict(Counter(row["color"] for row in assembly["placements"])),
        "unique_assembly_stl": 21, "assembly_bom_rows": 23, "plates": 14,
        "trial_quantity_separate_from_assembly": 7, "fit_master_count": 12,
        "nameplate": manifest["nameplate"],
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
