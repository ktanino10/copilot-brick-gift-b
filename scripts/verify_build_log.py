"""Verify approved photo bytes, absent metadata, unchanged print inputs and offline navigation."""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from PIL import Image
from playwright.sync_api import sync_playwright

from build_log_navigation import NAVIGATION, canonical_guide_hash
from build_photo_log import PHOTO_BATCHES, PROGRESS_ANCHOR, ROOT, approved_photos

USER_VIDEO_URL = "https://youtu.be/Lc_enNE3nng"
USER_VIDEO_ANCHOR = "post-processing-ultrasonic-2026-09-25"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class JournalDocument(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.links = []
        self.external_links = []
        self.external_link_attributes = []
        self.stage_headings = 0
        self.ids = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        require(tag not in ("script", "iframe", "object", "embed", "form", "base"),
                "The photo journal must remain a passive document.")
        if tag == "img":
            self.images.append(attrs)
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
            if attrs["href"].startswith(("http:", "https:", "//")):
                self.external_links.append(attrs["href"])
                self.external_link_attributes.append(attrs)
        if tag == "h3":
            self.stage_headings += 1
        if "id" in attrs:
            self.ids.add(attrs["id"])


def verify_user_video_link(document):
    require(document.external_links == [USER_VIDEO_URL],
            "Only one exact user-provided online video link is allowed in the journal.")
    attrs = document.external_link_attributes[0]
    require(attrs.get("target") == "_blank"
            and {"noopener", "noreferrer"} <= set(attrs.get("rel", "").split()),
            "The video link needs safe new-tab attributes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--browser-channel", choices=("chrome", "chromium", "msedge"))
    parser.add_argument("--static-only", action="store_true",
                        help="Run the approved documentation-only checks and record browser execution as NOT_RUN_ENVIRONMENT.")
    parser.add_argument("--report", type=Path, default=ROOT / "verification/build-log.json")
    args = parser.parse_args()
    approved = approved_photos()
    expected_stages = sum(batch["described_stages"] for batch in PHOTO_BATCHES)
    for name, photo in approved.items():
        path = ROOT / "docs" / name
        require(re.fullmatch(r"[a-z][a-z0-9-]+\.jpg", path.name) and sha(path) == photo["sha256"]
                and path.stat().st_size == photo["size_bytes"], f"Supplied image bytes differ:{name}")
        with Image.open(path) as image:
            image.load()
            require(image.format == "JPEG" and image.mode == "RGB" and getattr(image, "n_frames", 1) == 1
                    and not image.getexif() and set(image.info) <= {"jfif", "jfif_version", "jfif_unit", "jfif_density"}
                    and list(image.size) == photo["pixels"], f"Unexpected image metadata or format:{name}")
        require(photo["capture_date"] is None, "Do not infer a capture date from the supplied files.")
    for name in ("BUILD-LOG.md", "BUILD-LOG.html"):
        content = (ROOT / "docs" / name).read_text()
        document = JournalDocument()
        document.feed(content)
        require(document.stage_headings == expected_stages if name.endswith(".html")
                else len(re.findall(r"^### [1-5]\.", content, flags=re.MULTILINE)) == expected_stages,
                "The journal must retain each dated batch's described stages.")
        require(len(document.images) == len(approved), "All approved photos must appear once, not as invented extra milestones.")
        require(PROGRESS_ANCHOR in document.ids, "The new dated progress anchor is missing.")
        require("progress-2026-09-24" in document.ids, "The earlier dated progress link must remain valid.")
        require("これで完成ですね" in content and "制作過程の写真です" in content,
                "The user's construction and completion reports must be retained accurately.")
        require(USER_VIDEO_ANCHOR in document.ids and document.external_links == [USER_VIDEO_URL]
                and "視聴にはインターネット接続が必要です" in content,
                "The user-provided video must remain one explicit online-only reference link.")
        verify_user_video_link(document)
        expected = set(approved)
        require({image.get("src") for image in document.images} == expected
                and all(image.get("alt") for image in document.images), "Image links or accessible captions differ.")
        for link in document.links:
            if link == USER_VIDEO_URL:
                continue
            if link:
                target, _, fragment = link.partition("#")
                require((ROOT / "docs" / target).resolve().is_file() if target else fragment in document.ids,
                        f"Broken journal link:{link}")
    baseline = json.loads((ROOT / "verification/build-log-input-baseline.json").read_text())
    for filename, expected_hash in baseline["files"].items():
        require(sha(ROOT / filename) == expected_hash, f"Protected print/native/data input changed:{filename}")
    progress_baseline = json.loads((ROOT / "verification/build-log-progress-baseline.json").read_text())
    for filename, expected_hash in progress_baseline["files"].items():
        require(sha(ROOT / filename) == expected_hash, f"Prior design, media or photo changed:{filename}")
    guide = ROOT / "guide/index.html"
    require(guide.read_text().count(NAVIGATION) == 1
            and canonical_guide_hash(guide) == baseline["guide_entry_sha256"],
            "The guide changed beyond the documentation-only navigation.")
    previous = json.loads((ROOT / "verification/guide-browser.json").read_text())
    require(previous.get("canonical_guide_sha256", previous["entry_sha256"]) == canonical_guide_hash(guide),
            "Prior geometry/control verification does not apply to this unchanged base document.")

    errors, network = [], []
    browser_version = None
    if not args.static_only:
        browser_version = browser_checks(args, guide, approved, errors, network)
    require(not errors and not network, f"Offline journal errors/network activity:{errors}/{network}")
    html = (ROOT / "docs/BUILD-LOG.html").read_text()
    require("max-width:100%" in html and "@media(max-width:600px)" in html
            and "overflow-wrap:anywhere" in html and "connect-src 'none'" in html
            and not re.search(r"@import|url\(\s*['\"]?https?:", html),
            "Standard offline/responsive document constraints are missing.")
    sources = [ROOT / "docs/BUILD-LOG.md", ROOT / "docs/BUILD-LOG.html",
               *[ROOT / batch["directory"] / "manifest.json" for batch in PHOTO_BATCHES],
               *[ROOT / "docs" / name for name in approved]]
    report = {
        "status": "PASS_DOCUMENTATION_STATIC" if args.static_only else "PASS",
        "scope": "new photo documentation; prior3D report is not reused as a photo-log browser test",
        "browser": browser_version,
        "browser_channel": args.browser_channel if not args.static_only else None,
        "browser_execution": "NOT_RUN_ENVIRONMENT" if args.static_only else "PASS",
        "browser_limitation": (
            "Not run locally for this update because earlier local browser launches failed. No additional launch workarounds are attempted. The current approved public Pages workflow separately runs Linux HTTP and file checks; this static report does not claim that browser result."
            if args.static_only else None
        ),
        "follow_up": "Use the current Linux Pages workflow browser result; when the local environment is available this verifier can also run without --static-only.",
        "report_date": PHOTO_BATCHES[-1]["reported_date"], "photo_count": len(approved),
        "photo_batches": [{"reported_date": batch["reported_date"], "photo_count": batch["photo_count"]}
                         for batch in PHOTO_BATCHES],
        "described_stages": expected_stages, "latest_progress_anchor": PROGRESS_ANCHOR,
        "guide_entry_sha256": sha(guide), "guide_base_sha256": canonical_guide_hash(guide),
        "prior_unchanged_3d_report_reference": "verification/guide-browser.json",
        "all_image_files_decoded": True, "all_relative_image_paths_resolve": True,
        "standard_scrollable_responsive_css": True,
        "all_local_images_loaded_in_browser": None if args.static_only else True,
        "first_base_control_and_return_navigation": None if args.static_only else True,
        "external_network_requests": None if args.static_only else 0,
        "page_errors": None if args.static_only else 0,
        "mobile_browser_overflow": None if args.static_only else False,
        "photo_bytes_match_parent": True, "photo_metadata": "RGB single-frame JPEG; JFIF only",
        "capture_dates_inferred": False, "protected_input_hashes_unchanged": len(baseline["files"]),
        "prior_design_media_and_photo_hashes_unchanged": len(progress_baseline["files"]),
        "inputs_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for path in sources},
        "physical_evidence": "User-reported construction through September25 completion, with photographs showing the closed upper goggle frame and purple crown. Purple/yellow are observed photo colors, not changes to the design's magenta/green palette.",
        "formal_physical_validation": "NOT_PROVIDED",
        "full_figure_completion": "USER_REPORTED_WITH_COMPLETION_PHOTOS",
        "individual_150_part_inspection": "NOT_PROVIDED",
        "photo_to_STL_and_slicer_revision_match": "NOT_CONFIRMED",
        "user_provided_video": {
            "url": USER_VIDEO_URL, "anchor": USER_VIDEO_ANCHOR, "requires_network_to_watch": True,
            "embedded": False, "downloaded_or_rehosted": False,
            "conditions_or_results_independently_verified": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def browser_checks(args, guide, approved, errors, network):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **(
            {"channel": args.browser_channel} if args.browser_channel else {}
        ))
        version = browser.version
        context = browser.new_context(viewport={"width": 1280, "height": 960}, offline=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: network.append(request.url)
                if request.url.startswith(("http:", "https:")) else None)
        page.on("websocket", lambda socket: network.append(socket.url))
        page.goto(guide.as_uri(), wait_until="load", timeout=120000)
        page.locator('#guide-app[data-ready="true"]').wait_for(timeout=120000)
        page.locator("#start-first").click()
        state = page.evaluate("() => BrickAssemblyGuide.state()")
        require(state["activeId"] == "B-001" and state["selectedSlot"] == "B-black-02.3mf#3",
                "Documentation navigation interferes with the first-base control.")
        page.locator("#build-record-nav a").click()
        page.wait_for_load_state("load")
        require(page.url == (ROOT / "docs/BUILD-LOG.html").as_uri(), "The guide did not open the local journal.")
        page.locator("details").evaluate_all("elements => elements.forEach(element => {element.open = true})")
        page.locator(f"#{PROGRESS_ANCHOR}").wait_for(state="attached")
        page.evaluate("() => Promise.all([...document.images].map(image => image.decode()))")
        loaded = page.evaluate("""() => [...document.images].map(image => ({
            file: image.getAttribute('src'), complete: image.complete,
            width: image.naturalWidth, height: image.naturalHeight
        }))""")
        require(len(loaded) == len(approved) and all(image["complete"] and image["width"] > 0 for image in loaded),
                "Some local photos did not load.")
        for image in loaded:
            expected = approved[image["file"]]
            require([image["width"], image["height"]] == expected["pixels"], "Browser decoded different image dimensions.")
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshots / "photo-log-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        require(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"),
                "The photo journal overflows a narrow screen.")
        if args.screenshots:
            page.screenshot(path=str(args.screenshots / "photo-log-mobile.png"), full_page=True)
        page.get_by_role("link", name="3D工程へ", exact=True).click()
        page.locator('#guide-app[data-ready="true"]').wait_for(timeout=120000)
        require(page.evaluate("() => BrickAssemblyGuide.state().empty"), "Return navigation did not reopen the guide.")
        browser.close()
    return version


if __name__ == "__main__":
    main()
