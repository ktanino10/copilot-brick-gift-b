#!/usr/bin/env python3
"""Check the generated ZIP's extracted guide and an isolated HTML copy, with no network."""

import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import zipfile

from playwright.sync_api import sync_playwright

from build_print_kit import ARCHIVE, ROOT
from verify_guide_browser import api, assert_prefix, require, snapshot
from verify_kit import verify_package


def main():
    verify_package()
    mapping = json.loads((ROOT / "guide/index.mapping.json").read_text())
    work = ROOT / ".work"
    work.mkdir(exist_ok=True)
    requests, errors = [], []
    with TemporaryDirectory(prefix="B offline guide ", dir=work) as directory:
        destination = Path(directory)
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive.extractall(destination)
            members = len(archive.namelist())
        entry = destination / "guide/index.html"
        standalone = destination / "standalone 日本語.html"
        shutil.copyfile(entry, standalone)
        expected_hash = hashlib.sha256((ROOT / "guide/index.html").read_bytes()).hexdigest()
        require(hashlib.sha256(entry.read_bytes()).hexdigest() == expected_hash,
                "Extracted HTML is not the verified guide.")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(offline=True, service_workers="block",
                                              viewport={"width": 1280, "height": 1000})

                def requested(request):
                    if urlsplit(request.url).scheme in {"http", "https", "ws", "wss"}:
                        requests.append(request.url)

                def route_request(route):
                    if urlsplit(route.request.url).scheme in {"http", "https", "ws", "wss"}:
                        route.abort()
                    else:
                        route.continue_()

                context.on("request", requested)
                context.route("**/*", route_request)
                for path in (entry, standalone):
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda event: errors.append(event.text) if event.type == "error" else None)
                    page.on("websocket", lambda socket: requests.append(socket.url))
                    page.goto(path.as_uri(), wait_until="load")
                    page.locator('#guide-app:not([data-ready="false"])').wait_for(state="attached", timeout=180000)
                    require(page.locator("#guide-app").get_attribute("data-ready") == "true",
                            "Extracted/isolated HTML failed to start.")
                    require(snapshot(page)["assemblyPoses"] == [] and snapshot(page)["step"] == 0,
                            "Extracted guide is not initially empty.")
                    page.locator("#plate-select").select_option("B-black-02.3mf")
                    page.locator('#slot-list [data-slot="B-black-02.3mf#3"]').click()
                    require(snapshot(page)["candidateIds"] == ["B-001"], "Extracted first-base mapping failed.")
                    page.locator("#start-first").click()
                    page.locator("#motion-progress").focus()
                    page.keyboard.press("End")
                    require(snapshot(page)["seatedCount"] == 1, "Extracted guide did not seat the first base.")
                    page.locator("#step-select").select_option("28")
                    state = snapshot(page)
                    assert_prefix(state, mapping)
                    require(state["cursor"] == state["seatedCount"] == 150, "Extracted guide omitted final parts.")
                    api(page, "restart")
                    require(snapshot(page)["assemblyPoses"] == [], "Extracted guide did not reset.")
                    page.close()
            finally:
                browser.close()
    require(not requests and not errors, f"Offline extracted guide failed: {requests or errors}")
    print(json.dumps({
        "status": "PASS", "zip_members": members, "entry_sha256": expected_hash,
        "extracted_file_url": True, "isolated_html_file_url": True, "spaces_and_unicode_path": True,
        "external_network_requests": len(requests), "browser_errors": len(errors),
        "first_base": "B-black-02.3mf#3 -> B-001", "final_placements": 150,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
