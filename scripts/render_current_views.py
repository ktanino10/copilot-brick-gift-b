"""Capture only the current full-model views and front-module detail needed by the docs."""

import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "docs/images"
    captures = {}
    errors, network = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1100}, offline=True)
        page = context.new_page()
        page.set_default_timeout(120000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: network.append(request.url) if request.url.startswith(("http:", "https:")) else None)
        page.goto((ROOT / "guide/index.html").as_uri(), wait_until="load")
        page.locator('#guide-app[data-ready="true"]').wait_for()
        page.add_style_tag(content="#assembly-viewport{height:640px}")
        page.locator("#ghost").uncheck()

        def api(method, *args):
            return page.evaluate("([method,args]) => BrickAssemblyGuide[method](...args)", [method, args])

        def capture(name, view):
            api("setView", "assembly", view)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            encoded = page.locator("#assembly-canvas").evaluate("canvas => canvas.toDataURL('image/png')")
            image = Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))).convert("RGB")
            pixels = np.array(image, dtype=np.int16)
            content = np.max(np.abs(pixels - np.array([234, 240, 241])), axis=2) > 18
            yy, xx = np.where(content)
            if len(xx) < 100:
                raise ValueError("Current assembly render is empty.")
            image = image.crop((max(0, int(xx.min()) - 12), max(0, int(yy.min()) - 12),
                                min(image.width, int(xx.max()) + 13), min(image.height, int(yy.max()) + 13)))
            image.save(output / name)
            state = api("state")
            captures[name] = {
                "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest(),
                "view": view, "cursor": state["cursor"], "progress": state["progress"],
                "seated_count": state["seatedCount"], "image_dimensions": list(image.size),
            }
            print(f"Captured{name}:{image.width}x{image.height}.", flush=True)

        api("setCursor", 150)
        capture("B-hero.png", "iso")
        capture("B-overview-front.png", "front")
        capture("B-overview-right.png", "side")
        capture("B-overview-top.png", "top")
        api("setCursor", 23)
        api("setProgress", 1)
        capture("B-base-front.png", "front")
        api("setCursor", 19)
        api("setProgress", .65)
        capture("B-front-release.png", "iso")
        browser.close()
    if errors or network:
        raise ValueError(f"Render errors or unexpected network activity:{errors}/{network}")
    (ROOT / "verification/current-views.json").write_text(json.dumps({
        "revision": "4.1-B-legibility.1", "source": "actual current STL meshes in the offline orthographic viewer",
        "entry_sha256": hashlib.sha256((ROOT / "guide/index.html").read_bytes()).hexdigest(),
        "external_requests": 0, "page_errors": [], "captures": captures,
    }, indent=2) + "\n")
    print(json.dumps(captures, indent=2))


if __name__ == "__main__":
    main()
