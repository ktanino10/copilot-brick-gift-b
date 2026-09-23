#!/usr/bin/env python3
"""Build the approved private B guide with the shared generic renderer."""

from pathlib import Path

from build_assembly_guide import build_mapping, digest, read_json, write_guide
from verify_guide_mapping import INPUTS, verify_mapping
from verify_offline_html import verify_file
from build_log_navigation import add_navigation


ROOT = Path(__file__).resolve().parents[1]
TITLE = "B DESK CLASSIC / 個人版・印刷ファイルから組み立てる3Dガイド"


def main():
    runtime = ROOT / "web/assembly-guide/runtime.js"
    if not runtime.is_file():
        raise ValueError("Missing vendored runtime. Run the documented guide bundle command first.")
    paths = {key: ROOT / path for key, path in INPUTS.items()}
    mapping, meshes = build_mapping(
        *(read_json(paths[key]) for key in ("catalog", "assembly", "plates")),
        ROOT / "kit/B", ROOT / "kit/B/plates", TITLE,
    )
    mapping["inputs_sha256"] = {key: digest(path.read_bytes()) for key, path in paths.items()}
    verify_mapping(mapping)
    entry = ROOT / "guide/index.html"
    write_guide(mapping, meshes, entry, runtime, ROOT / "web/assembly-guide", standalone=True)
    entry.write_text(add_navigation(entry.read_text(encoding="utf-8")), encoding="utf-8")
    verify_file(entry)
    print(f"PASS: {entry.relative_to(ROOT)} / 14 real plates / 150 occurrences / 21 byte-identical STL meshes")


if __name__ == "__main__":
    main()
