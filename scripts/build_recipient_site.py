"""Build the allowlisted recipient Pages site without copying the repository root."""

import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import posixpath
from pathlib import Path
import shutil
import subprocess
from urllib.parse import unquote, urlsplit, urlunsplit

import markdown
from markdown.extensions.toc import slugify_unicode

from build_photo_log import PHOTO_BATCHES, PROGRESS_ANCHOR, STYLE, approved_photos
from user_video import CLEANING_VIDEO, PRINTING_VIDEO, USER_VIDEO_EMBED_ORIGIN, USER_VIDEOS

ROOT = Path(__file__).resolve().parents[1]
REPO = "ktanino10/copilot-brick-gift-b"
PAGE_SOURCES = {
    "docs/PRINTING.md": ("docs/PRINTING.html", "印刷の仕方"),
    "docs/ASSEMBLY.md": ("docs/ASSEMBLY.html", "組立・交換・分解"),
    "docs/GUIDE.md": ("docs/GUIDE.html", "3D工程の使い方"),
    "docs/FILES.md": ("docs/FILES.html", "部品とファイルの対応"),
    "docs/STEPS.md": ("docs/STEPS.html", "全28工程"),
    "docs/TRIAL.md": ("docs/TRIAL.html", "少量試作"),
    "docs/NAMEPLATE-V2.md": ("docs/NAMEPLATE-V2.html", "文字銘板の改訂"),
    "docs/BUILD-LOG.md": ("docs/BUILD-LOG.html", "実写真の制作記録"),
    "notices/README.md": ("about.html", "権利・公開範囲"),
}
DATA_FILES = {
    "kit/B/bom.csv", "kit/B/steps.csv", "kit/B/part-map.csv", "kit/B/assembly.json",
    "kit/B/drawings.pdf", "kit/fit/interface.pdf", "kit/fit/interface.svg",
    "kit/fit/front-interface.svg", "kit/fit-log.csv", "kit/trial/bom.csv",
}
EXTRA_STYLE = """
.site-nav{display:flex;flex-wrap:wrap;gap:10px 22px;padding:14px 0;border-bottom:1px solid #c9d4dc;margin-bottom:28px}
.site-nav a{font-weight:650;text-decoration:none}.hero{display:grid;grid-template-columns:1.4fr 1fr;gap:30px;align-items:center}
.hero h1{font-size:clamp(30px,5vw,52px)}.hero img{max-height:420px;margin:auto;border:0}
.hero figure{margin:0}.hero figcaption{font-size:13px;color:#506375;text-align:center;margin-top:10px}
.eyebrow{font-size:13px;letter-spacing:.12em;color:#006d75;font-weight:750}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin:28px 0}
.card{padding:22px;border:1px solid #c9d4dc;border-radius:12px;background:#fff}.card h2{border:0;margin:0 0 12px;padding:0;font-size:21px}
.button{display:inline-block;padding:10px 18px;border-radius:7px;background:#006d75;color:white;font-weight:700;text-decoration:none}
.note{padding:16px 20px;border-left:4px solid #dd7247;background:#fff4e9;margin:24px 0}.small{font-size:14px;color:#506375}
.skip{position:absolute;left:-10000px}.skip:focus{position:static}
.user-video{width:100%;max-width:900px;aspect-ratio:16/9;margin:20px 0;background:#172433}
.user-video iframe{display:block;width:100%;height:100%;border:0}
@media(max-width:720px){.hero,.cards{grid-template-columns:1fr}.hero img{max-height:330px}.site-nav{gap:8px 14px}.card{padding:17px}}
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(output, target):
    return posixpath.relpath(target, posixpath.dirname(output) or ".")


class SiteBuilder:
    def __init__(self, output, commit):
        self.output = output
        self.commit = commit
        self.files = {}
        self.photo_paths = {"docs/" + path for path in approved_photos()}
        self.photo_manifest_paths = {batch["directory"] + "/manifest.json" for batch in PHOTO_BATCHES}

    def emit(self, destination, data, source):
        path = self.output / destination
        if path.resolve().is_relative_to(self.output.resolve()) is False:
            raise ValueError("Site output escapes its dedicated directory.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.files[destination] = {"path": destination, "source": source, "bytes": len(data), "sha256": digest(data)}

    def allowed_asset(self, path):
        suffix = Path(path).suffix.lower()
        if path in DATA_FILES or path in self.photo_manifest_paths or path == "notices/THREE-LICENSE.txt":
            return True
        if path.startswith("docs/images/") and suffix in (".png", ".svg", ".gif"):
            return True
        if path in self.photo_paths:
            return True
        return path.startswith("kit/B/drawings/") and suffix == ".svg"

    def asset(self, path):
        source = ROOT / path
        if (not self.allowed_asset(path) or not source.is_file() or source.is_symlink()
                or source.resolve() != source):
            raise ValueError(f"Unapproved/missing active site asset:{path}")
        if path not in self.files:
            self.emit(path, source.read_bytes(), path)
        return path

    def url(self, value, source, output, active=False):
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            if active:
                raise ValueError("Active images/styles must be allowlisted local assets.")
            if parsed.scheme != "https":
                raise ValueError("Only explicit HTTPS external links are permitted.")
            return value
        path = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path))) if parsed.path else source
        if path.startswith("../"):
            raise ValueError("Document link escapes the repository.")
        if path == "README.md":
            target = "index.html"
        elif path in PAGE_SOURCES:
            target = PAGE_SOURCES[path][0]
        elif path == "docs/BUILD-LOG.html":
            target = "docs/BUILD-LOG.html"
        elif path == "guide/index.html":
            target = path
        elif self.allowed_asset(path):
            target = self.asset(path)
        else:
            if active or not (ROOT / path).exists():
                raise ValueError(f"Unresolved document target:{path}")
            base = "tree" if (ROOT / path).is_dir() else "blob"
            return urlunsplit(("https", "github.com", f"/{REPO}/{base}/{self.commit}/{path}", parsed.query, parsed.fragment))
        return urlunsplit(("", "", relative(output, target), parsed.query, parsed.fragment))

    def navigation(self, output):
        links = [
            ("index.html", "トップ"), ("guide/index.html", "3D工程"),
            ("docs/PRINTING.html", "印刷"), ("docs/ASSEMBLY.html", "組立"),
            ("docs/BUILD-LOG.html", "制作記録"), ("about.html", "公開範囲・権利"),
        ]
        return '<nav class="site-nav" aria-label="案内">' + "".join(
            f'<a href="{escape((f"https://ktanino10.github.io/copilot-brick-gift-b/{target}" if output == "404.html" else relative(output, target)), quote=True)}">{label}</a>' for target, label in links
        ) + "</nav>"

    def document(self, output, title, body):
        has_video = output == "docs/BUILD-LOG.html"
        referrer = "strict-origin-when-cross-origin" if has_video else "no-referrer"
        frame_policy = f"frame-src {USER_VIDEO_EMBED_ORIGIN}; " if has_video else ""
        content = (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="referrer" content="{referrer}">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'img-src \'self\' data:; style-src \'unsafe-inline\'; connect-src \'none\'; '
            'object-src \'none\'; base-uri \'none\'; form-action \'none\'; '
            f'{frame_policy}">'
            f"<title>{escape(title)} | 個人Bの作り方</title><style>{STYLE}{EXTRA_STYLE}</style></head><body>"
            '<a class="skip" href="#content">本文へ</a><main>'
            + self.navigation(output) + '<article id="content">' + body + "</article>"
            + '<footer>個人向けBの公開案内です。9/25にゴーグル・頭頂までの完成写真と本人の完成報告が届きました。'
            '制作の完成と、寸法・荷重・耐久等の測定記録は分けています。公開内容は第三者にコピー・保存され得ます。'
            f'<p>配信元: <a href="https://github.com/{REPO}/commit/{self.commit}">{self.commit[:12]}</a></p>'
            "</footer></main></body></html>\n"
        )
        return content.encode()

    def build(self):
        for source, (output, title) in PAGE_SOURCES.items():
            text = (ROOT / source).read_text()
            body = markdown.markdown(text, extensions=["tables", "fenced_code", "md_in_html", "toc"],
                                     extension_configs={"toc": {"slugify": slugify_unicode}})
            rewriter = LinkRewriter(self, source, output)
            rewriter.feed(body)
            rendered = "".join(rewriter.result)
            if output == "docs/BUILD-LOG.html":
                for item in USER_VIDEOS:
                    if rendered.count(item["placeholder"]) != 1:
                        raise ValueError("Expected one placeholder for each exact user video.")
                    embed = (
                        f'<div id="{item["placeholder_id"]}" class="user-video">'
                        f'<iframe id="{item["frame_id"]}" name="{item["frame_id"]}" '
                        f'src="{item["embed_url"]}" title="{escape(item["title"], quote=True)}" '
                        'width="560" height="315" loading="lazy" '
                        'referrerpolicy="strict-origin-when-cross-origin" '
                        'allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>'
                    )
                    rendered = rendered.replace(item["placeholder"], embed, 1)
            intro = (
                '<p class="note">このWeb版はURLからそのまま閲覧できます。'
                f'<a href="{relative(output, "guide/index.html")}">3D工程を開く</a> ／ '
                f'<a href="https://github.com/{REPO}/blob/{self.commit}/downloads/B-personal-print-kit.zip">'
                '印刷キットを保存</a>。キットを保存した場合は展開してから使います。</p>'
            )
            self.emit(output, self.document(output, title, intro + rendered), source)
        hero = self.asset("docs/images/B-hero.png")
        photograph = self.asset("docs/images/build-log-2026-09-23/front-modules-installed.jpg")
        latest_photo = self.asset("docs/images/build-log-2026-09-24/face-top-row.jpg")
        completed_photo = self.asset("docs/images/build-log-2026-09-25/finished-portrait.jpg")
        body = (
            '<section class="hero"><div><p class="eyebrow">B DESK CLASSIC / PERSONAL BUILD GUIDE</p>'
            '<h1>つくる過程も、<br>贈る楽しみに。</h1>'
            '<p>このBモデルの説明、印刷と組立の手順、部品を探せる3D工程、実写真の制作記録をまとめました。'
            '閲覧にGitHubへのログインやアプリのインストールは不要です。</p>'
            '<p><a class="button" href="guide/index.html">3Dで工程を見る</a></p>'
            '<p class="small">Same icon, New adventures<br>github.com/tomokota</p></div>'
            f'<figure><a href="docs/BUILD-LOG.html#{PROGRESS_ANCHOR}"><img src="{completed_photo}" '
            'alt="9/25の実物完成写真。ゴーグル上枠と紫の頭頂、個人銘板付き台座までそろった姿。背景処理済み"></a>'
            '<figcaption>実物の完成写真 · 2026-09-25報告<br>背景を切り取り・マスク処理しています。</figcaption></figure></section>'
            '<h2>今回の制作の5工程</h2>'
            '<section class="cards" aria-label="企画から組み立てまでの5工程">'
            '<div class="card"><h2>1. 企画</h2><p>贈って飾る模型の形・用途・大きさを考える。</p>'
            '<a href="docs/BUILD-LOG.html#process-planning">企画・仕様へ →</a></div>'
            '<div class="card"><h2>2. 設計</h2><p>FreeCADの分割・取付け、設計CG、図面と銘板改良。</p>'
            '<a href="docs/BUILD-LOG.html#process-design">設計資料へ →</a></div>'
            '<div class="card"><h2>3. 3Dプリント</h2><p>設計したパーツを印刷。ユーザー提供動画をページ内で再生。</p>'
            f'<a href="docs/BUILD-LOG.html#{PRINTING_VIDEO["anchor"]}">印刷動画へ →</a></div>'
            '<div class="card"><h2>4. 超音波洗浄</h2><p>今回の印刷後の後処理。ページ内の動画で見る。</p>'
            f'<a href="docs/BUILD-LOG.html#{CLEANING_VIDEO["anchor"]}">洗浄動画へ →</a></div>'
            '<div class="card"><h2>5. アッセンブリー</h2><p>土台から顔・ゴーグルを積み上げて完成へ。</p>'
            '<a href="docs/BUILD-LOG.html#process-assembly">実写真と3D工程へ →</a></div></section>'
            '<p class="small">ユーザーが示した今回の制作フローです。写真の日付記録は保持し、未提示の印刷・洗浄条件を補っていません。</p>'
            '<div class="note"><strong>最初の台座はblack-01ではありません。</strong>'
            '<p>B-black-02.3mfのslot3にある大きな1枚がB-001です。印刷順と組立順を分けて案内します。</p></div>'
            '<div class="note"><strong>2026-09-25：ついに完成。「これで完成ですね」とご報告いただきました。</strong>'
            f'<p><a href="docs/BUILD-LOG.html#{PROGRESS_ANCHOR}">ゴーグルの組立から、上枠と紫の頭頂がそろった完成写真へ →</a></p>'
            '<p class="small">新しい制作過程と完成の8枚を追記。前の16枚も、各日の記録として残しています。</p></div>'
            '<h2>9/24の記録：顔下部の途中</h2>'
            f'<a href="docs/BUILD-LOG.html#progress-2026-09-24"><img src="{latest_photo}" alt="9/24時点の顔下部。黒い層と紫色の輪郭、黄色い縦2列が見える途中写真"></a>'
            '<h2>9/23の記録：土台と前面まで</h2>'
            f'<a href="docs/BUILD-LOG.html"><img src="{photograph}" alt="2行銘板と右ロゴ付きの台座。ユーザー提供の実写真"></a>'
            '<p>2026-09-23の本人報告と写真です。顔・ゴーグルを含む全体完成や、使用ファイルの版・寸法・保持力の実測を証明する写真ではありません。</p>'
            '<h2>このBについて</h2><p>設計上は150部品、黒い5段台座、独立した銘板と右ロゴ。'
            '文字銘板は2行を維持し、下段10 mm・白い浮彫1.2 mmへ改訂しています。</p>'
            f'<details><summary>設計の完成CGを見る（実物写真とは別）</summary><img src="{hero}" '
            'alt="設計上の配色によるBの完成CG。上の実物写真ではない">'
            '<p class="small">既存の設計CGです。実制作の紫・黄色に合わせた再生成はしていません。</p></details>'
            '<p><a href="docs/NAMEPLATE-V2.html">銘板の比較と小試験片</a> ／ '
            '<a href="docs/FILES.html">全ファイルと部品の対応</a> ／ <a href="docs/STEPS.html">全28工程</a></p>'
            '<p class="small">模型の寸法は変えていません。印刷は配布データのmm・100%を維持し、'
            '必ず実機設定とスライス結果を確認します。</p>'
        )
        self.emit("index.html", self.document("index.html", "説明・作り方・工程・制作記録", body), "curated landing")
        guide = (ROOT / "guide/index.html").read_text()
        banner = (
            '<nav aria-label="公開案内" style="padding:12px 24px;background:#fff">'
            '<a href="../index.html">個人Bの案内トップへ</a> · '
            '<a href="../docs/ASSEMBLY.html">組立手順</a> · '
            '<a href="../docs/BUILD-LOG.html">実写真の制作記録</a></nav>'
        )
        if guide.count("<body>") != 1:
            raise ValueError("Unexpected guide document structure.")
        self.emit("guide/index.html", guide.replace("<body>", "<body>" + banner, 1).encode(), "guide/index.html")
        self.asset("notices/THREE-LICENSE.txt")
        self.emit(".nojekyll", b"", "Pages configuration")
        self.emit("404.html", self.document("404.html", "ページが見つかりません", '<h1>ページが見つかりません</h1><p><a href="https://ktanino10.github.io/copilot-brick-gift-b/">案内トップへ戻る</a></p>'), "curated error page")
        manifest = {"repository": REPO, "source_commit": self.commit, "site_public": True,
                    "scope": "current recipient-facing content only", "files": list(self.files.values())}
        (self.output / "site-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


class LinkRewriter(HTMLParser):
    def __init__(self, builder, source, output):
        super().__init__(convert_charrefs=False)
        self.builder, self.source, self.output = builder, source, output
        self.result = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "iframe", "object", "embed", "form", "base"):
            raise ValueError(f"Unexpected active document tag:{tag}")
        values = []
        for key, value in attrs:
            if key in ("href", "src"):
                value = self.builder.url(value, self.source, self.output, active=key == "src")
            values.append(key if value is None else f'{key}="{escape(value, quote=True)}"')
        self.result.append("<" + tag + (" " + " ".join(values) if values else "") + ">")

    def handle_endtag(self, tag):
        self.result.append(f"</{tag}>")

    def handle_data(self, data):
        self.result.append(data)

    def handle_entityref(self, name):
        self.result.append("&" + name + ";")

    def handle_charref(self, name):
        self.result.append("&#" + name + ";")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    parser.add_argument("--commit")
    args = parser.parse_args()
    output = args.output.resolve()
    if output not in (ROOT / "_site", ROOT / "build/recipient-site"):
        raise ValueError("Use the fixed, dedicated generated site directory.")
    if output.exists():
        if not (output / "site-manifest.json").is_file():
            raise ValueError("Refusing to clean an unrecognized output directory.")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    commit = args.commit or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("Expected a full source commit SHA.")
    SiteBuilder(output, commit).build()
    print(f"Built the curated recipient site in {output.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
