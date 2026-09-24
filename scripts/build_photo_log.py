"""Build the offline reading page and link it without changing the existing 3D guide."""

import hashlib
from html import escape
import json
from pathlib import Path

import markdown

from build_log_navigation import add_navigation, base_document

ROOT = Path(__file__).resolve().parents[1]
PHOTO_BATCHES = (
    {
        "directory": "docs/images/build-log-2026-09-23",
        "manifest_sha256": "7c7f87ac43ae37208c0a50ca52a933f57b26d4797ab81c716a4aee6d28993d47",
        "photo_count": 9,
        "described_stages": 5,
        "reported_date": "2026-09-23",
    },
    {
        "directory": "docs/images/build-log-2026-09-24",
        "manifest_sha256": "86759288e06b747fa864441547329aa5dc107a69e8c8ca77552b3356343284f8",
        "photo_count": 7,
        "described_stages": 4,
        "reported_date": "2026-09-24",
    },
)
PROGRESS_ANCHOR = "progress-2026-09-24"
JOURNAL_TITLE = "Bの制作記録 — 文字試作・土台から顔下部の途中まで"


def approved_photos():
    result = {}
    for batch in PHOTO_BATCHES:
        directory = ROOT / batch["directory"]
        raw_manifest = (directory / "manifest.json").read_bytes()
        if hashlib.sha256(raw_manifest).hexdigest() != batch["manifest_sha256"]:
            raise ValueError("The approved parent photo manifest was changed.")
        manifest = json.loads(raw_manifest)
        if len(manifest["photos"]) != batch["photo_count"]:
            raise ValueError("The photo batch does not match the approved count.")
        expected_files = {"manifest.json"}
        for photo in manifest["photos"]:
            path = directory / photo["path"]
            if path.name != photo["id"] + ".jpg" or path.parent != directory or path.is_symlink():
                raise ValueError("Unexpected image path in the approved handoff.")
            if hashlib.sha256(path.read_bytes()).hexdigest() != photo["sha256"]:
                raise ValueError("Do not reprocess the parent's approved image derivatives.")
            key = path.relative_to(ROOT / "docs").as_posix()
            if key in result:
                raise ValueError("Duplicate journal photo.")
            result[key] = photo
            expected_files.add(path.name)
        if {path.name for path in directory.iterdir()} != expected_files:
            raise ValueError("Only approved photos and their neutral manifest belong in the batch directory.")
    return result

STYLE = """
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f3f5f1;color:#172433;
font:16px/1.85 system-ui,-apple-system,"Yu Gothic",sans-serif}main{max-width:1060px;margin:auto;padding:28px 28px 60px}
h1{font-size:clamp(25px,4vw,38px);line-height:1.4}h2{margin-top:36px;padding-top:12px;border-top:1px solid #c9d4dc}
h3{font-size:22px;margin-top:40px}a{color:#006d75;overflow-wrap:anywhere}a:focus-visible,summary:focus-visible{
outline:3px solid #b05c00;outline-offset:4px}img{display:block;max-width:100%;height:auto;max-height:580px;
object-fit:contain;margin:18px 0;border:1px solid #d5dce2;background:#eaf0f1}
table{border-collapse:collapse;width:100%;font-size:14px;table-layout:fixed}th,td{border:1px solid #c9d4dc;
padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e3efed}
details{padding:14px 20px;background:#fff;border:1px solid #c9d4dc;border-radius:8px}
summary{cursor:pointer;font-weight:700}code{overflow-wrap:anywhere}footer{color:#526678;font-size:13px;margin-top:32px}
@media(max-width:600px){main{padding:18px 14px 40px}body{font-size:15px}table{font-size:12px}th,td{padding:7px}
img{max-height:460px}details{padding:12px}h3{font-size:20px}}
"""


def main():
    photos = approved_photos()
    source = ROOT / "docs/BUILD-LOG.md"
    body = markdown.markdown(source.read_text(), extensions=["tables", "fenced_code", "md_in_html"])
    title = JOURNAL_TITLE
    document = (
        '<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'img-src \'self\' file: data:; style-src \'unsafe-inline\'; connect-src \'none\'; '
        'object-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head><body><main>"
        + body
        + '<footer>公開許可済みの個人版制作記録。掲載順は説明順です。撮影日時・版・実測条件は未照合です。'
        '図面の設計値や3Dの説明用の動きと、写真で確認できる状態を分けてください。</footer>'
        "</main></body></html>\n"
    )
    (ROOT / "docs/BUILD-LOG.html").write_text(document, encoding="utf-8")
    guide = ROOT / "guide/index.html"
    before = guide.read_text(encoding="utf-8")
    after = add_navigation(before)
    if base_document(before) != base_document(after):
        raise ValueError("The documentation link must not change the guide or embedded geometry.")
    guide.write_text(after, encoding="utf-8")
    print(f"Built the offline {len(photos)}-photo journal and added only the fixed documentation navigation.")


if __name__ == "__main__":
    main()
