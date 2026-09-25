"""Validate the published artifact boundary and optionally exercise it in an isolated browser."""

import argparse
import hashlib
from html.parser import HTMLParser
import http.server
import json
from pathlib import Path
import re
import threading
from urllib.parse import unquote, urlsplit

from PIL import Image

from build_recipient_site import PAGE_SOURCES, ROOT, SiteBuilder
from build_photo_log import PROGRESS_ANCHOR


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.images = [], set(), []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag == "img":
            self.images.append(attrs["src"])
            self.links.append(attrs["src"])
        if tag in ("iframe", "object", "embed", "form", "base"):
            raise ValueError(f"Unexpected active site tag:{tag}")


def verify(root):
    manifest = json.loads((root / "site-manifest.json").read_text())
    listed = {row["path"]: row for row in manifest["files"]}
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != set(listed) | {"site-manifest.json"}:
        raise ValueError("The site artifact includes unlisted or missing files.")
    policy = SiteBuilder(root, manifest["source_commit"])
    allowed_generated = {"index.html", "404.html", ".nojekyll", "guide/index.html"} | {
        page[0] for page in PAGE_SOURCES.values()
    }
    forbidden = re.compile(rb"/(?:Users|home|Applications)/[A-Za-z0-9_. -]+/|PXL_[0-9]{8}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    documents = {}
    for name, record in listed.items():
        path = root / name
        if path.is_symlink() or (name not in allowed_generated and not policy.allowed_asset(name)):
            raise ValueError(f"File is outside the Pages allowlist:{name}")
        data = path.read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"Site asset hash differs:{name}")
        if path.suffix in (".html", ".json", ".svg", ".txt") and forbidden.search(data):
            raise ValueError(f"Private machine path, raw photo name or credential-like value:{name}")
        if path.suffix == ".jpg":
            with Image.open(path) as image:
                image.load()
                if image.getexif() or set(image.info) - {"jfif", "jfif_version", "jfif_unit", "jfif_density"}:
                    raise ValueError("Unexpected photograph metadata.")
        if path.suffix == ".html":
            document = Document()
            document.feed(data.decode())
            documents[name] = document
    checked_links = 0
    for name, document in documents.items():
        for link in document.links:
            parsed = urlsplit(link)
            if parsed.scheme:
                if parsed.scheme != "https":
                    raise ValueError(f"Unsupported external link:{link}")
                continue
            target = (root / name).parent / unquote(parsed.path) if parsed.path else root / name
            target = target.resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                raise ValueError(f"Broken relative site link:{name} -> {link}")
            if parsed.fragment and target.suffix == ".html":
                if unquote(parsed.fragment) not in documents[target.relative_to(root.resolve()).as_posix()].ids:
                    raise ValueError(f"Broken HTML fragment:{name} -> {link}")
            checked_links += 1
    log = documents["docs/BUILD-LOG.html"]
    expected_photos = {path.removeprefix("docs/") for path in policy.photo_paths}
    if len(log.images) != len(expected_photos) or set(log.images) != expected_photos:
        raise ValueError("The dated journal does not contain exactly the approved photograph batches.")
    if PROGRESS_ANCHOR not in log.ids:
        raise ValueError("The latest dated progress anchor is missing from the public page.")
    if "progress-2026-09-24" not in log.ids:
        raise ValueError("Do not break the previous dated journal link.")
    log_text = (root / "docs/BUILD-LOG.html").read_text()
    if "これで完成ですね" not in log_text or "制作過程の写真です" not in log_text:
        raise ValueError("The current journal must include the user's actual completion and construction reports.")
    completed_photo = "docs/images/build-log-2026-09-25/finished-portrait.jpg"
    if completed_photo not in documents["index.html"].images:
        raise ValueError("The landing page is missing the authorized actual completion photograph.")
    if "実物の完成写真" not in (root / "index.html").read_text():
        raise ValueError("The completion photo must be labeled as an actual photograph, not a CG.")
    return {"status": "PASS_STATIC", "files": len(actual), "relative_links": checked_links,
            "photo_count": len(expected_photos), "latest_progress_anchor": PROGRESS_ANCHOR,
            "source_commit": manifest["source_commit"]}


def browser_check(root):
    from playwright.sync_api import sync_playwright
    prefix = "/copilot-brick-gift-b"
    expected_count = len(SiteBuilder(root, "").photo_paths)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            clean = unquote(urlsplit(path).path)
            if not clean.startswith(prefix + "/"):
                return str(root / "__not_found__")
            target = (root / clean[len(prefix) + 1:]).resolve()
            if not target.is_relative_to(root.resolve()):
                return str(root / "__not_found__")
            return str(target)

        def log_message(self, format, *args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}{prefix}/"
    errors, failures, external = [], [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 960})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed", lambda request: failures.append(request.url))
            page.on("request", lambda request: external.append(request.url) if request.url.startswith("http") and not request.url.startswith(base) else None)
            page.goto(base, wait_until="load")
            page.locator('img[src="docs/images/build-log-2026-09-25/finished-portrait.jpg"]').click()
            page.locator(f"#{PROGRESS_ANCHOR}").wait_for(state="attached")
            if urlsplit(page.url).fragment != PROGRESS_ANCHOR:
                raise ValueError("The actual completion photo does not link to the dated completion record.")
            page.goto(base, wait_until="load")
            page.get_by_role("link", name="3Dで工程を見る", exact=True).click()
            page.locator('#guide-app[data-ready="true"]').wait_for(timeout=120000)
            page.locator("#start-first").click()
            state = page.evaluate("() => BrickAssemblyGuide.state()")
            if state["activeId"] != "B-001" or state["selectedSlot"] != "B-black-02.3mf#3":
                raise ValueError("The recipient 3D guide does not start at the actual first base.")
            page.goto(base + "docs/BUILD-LOG.html#" + PROGRESS_ANCHOR, wait_until="load")
            page.locator(f"#{PROGRESS_ANCHOR}").wait_for(state="attached")
            page.locator("details").evaluate_all("elements => elements.forEach(element => {element.open=true})")
            page.evaluate("() => Promise.all([...document.images].map(image => image.decode()))")
            images = page.evaluate("() => [...document.images].map(image => ({ok:image.complete&&image.naturalWidth>0}))")
            if len(images) != expected_count or not all(image["ok"] for image in images):
                raise ValueError("Some recipient build photos failed to load.")
            for path in ("", "docs/PRINTING.html", "docs/ASSEMBLY.html", "docs/BUILD-LOG.html"):
                page.goto(base + path, wait_until="load")
                page.set_viewport_size({"width": 390, "height": 844})
                if not page.evaluate("() => document.documentElement.scrollWidth <= innerWidth+1"):
                    raise ValueError(f"Mobile overflow:{path}")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    if errors or failures or external:
        raise ValueError(f"Site errors/failed or external requests:{errors}/{failures}/{external}")
    return {"browser": "PASS", "first_base": "B-black-02.3mf#3 -> B-001",
            "photographs_loaded": expected_count, "latest_progress_anchor": PROGRESS_ANCHOR,
            "completion_photo_navigation": True,
            "page_errors": 0, "external_requests": 0, "mobile_overflow": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    root = args.site.resolve()
    result = verify(root)
    if args.browser:
        result.update(browser_check(root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
