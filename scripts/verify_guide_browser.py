#!/usr/bin/env python3
"""Exercise the actual offline guide in Chromium, optionally capturing its first 24 parts."""

import argparse
import base64
import hashlib
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

from verify_guide_mapping import verify_embedded, verify_mapping
from verify_offline_html import verify_file
from build_log_navigation import canonical_guide_hash


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def api(page, method, *args):
    return page.evaluate("([method, args]) => window.BrickAssemblyGuide[method](...args)", [method, args])


def snapshot(page):
    sample = page.evaluate("""() => {
      const state = window.BrickAssemblyGuide.state(), button = document.querySelector('#play');
      return { state, label: button.textContent, pressed: button.getAttribute('aria-pressed') };
    }""")
    state = sample["state"]
    require(sample["pressed"] == str(state["playing"]).lower()
            and (sample["label"] == "一時停止" if state["playing"] else sample["label"].startswith("再生")),
            "Playback state and its visible button/aria-pressed disagree.")
    return state


def wait_for_state(page, condition, message, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = snapshot(page)
        if condition(state):
            return state
        page.wait_for_timeout(75)
    raise AssertionError(message)


def same_vector(actual, expected):
    return len(actual) == len(expected) and all(
        math.isclose(a, b, rel_tol=0, abs_tol=1e-7) for a, b in zip(actual, expected)
    )


def assert_prefix(state, mapping):
    expected = mapping["placements"][:state["cursor"]]
    require(state["completedIds"] == [row["id"] for row in expected], "Placed prefix changed or duplicated.")
    poses = {row["id"]: row for row in state["assemblyPoses"]}
    require(len(poses) == len(state["assemblyPoses"]), "Rendered assembly has duplicate instances.")
    for row in expected:
        require(row["id"] in poses, f"Previously placed part disappeared: {row['id']}")
        require(same_vector(poses[row["id"]]["position"], row["position"])
                and same_vector(poses[row["id"]]["rotation"], row["rotation"]),
                f"Previously placed transform changed: {row['id']}")
    require(state["renderError"] is None, "Viewer reported a rendering error.")


def canvas_image(page, scene):
    encoded = page.locator(f"#{scene}-canvas").evaluate("(canvas) => canvas.toDataURL('image/png')")
    return Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))).convert("RGB")


def assert_framed(page, scene):
    image = np.asarray(canvas_image(page, scene), dtype=np.int16)
    require(image.shape[0] >= 100 and image.shape[1] >= 100, f"{scene} viewport is unusably small.")
    background = np.array([234, 240, 241])
    content = np.max(np.abs(image - background), axis=2) > 18
    rows, columns = np.where(content)
    require(len(rows) > 50, f"{scene} canvas contains no visible geometry.")
    require(rows.min() > 1 and columns.min() > 1
            and rows.max() < image.shape[0] - 2 and columns.max() < image.shape[1] - 2,
            f"{scene} geometry reaches the viewport edge at the fitted camera.")


def capture_media(page, mapping):
    print("Capturing the actual viewer's empty table and first 24 placements...", flush=True)
    page.set_viewport_size({"width": 1280, "height": 1100})
    page.locator("#ghost").uncheck()
    page.locator("#plate-isolate").uncheck()
    api(page, "setView", "plate", "iso")
    api(page, "setView", "assembly", "iso")
    api(page, "setStep", 0)
    card = page.locator("#capture-card")
    output = ROOT / "docs/images"
    frames, durations = [], []

    def frame(duration):
        image = Image.open(io.BytesIO(card.screenshot(animations="disabled"))).convert("RGB")
        if image.width > 1100:
            image = image.resize((1100, round(image.height * 1100 / image.width)), Image.Resampling.LANCZOS)
        frames.append(image.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
        durations.append(duration)

    frame(900)
    for placement in mapping["placements"][:24]:
        api(page, "setCursor", placement["index"])
        samples = [0, .14, .28, .42, .55, .75, 1] if placement["role"] == "front_module" else [0, .5, 1]
        for progress in samples:
            api(page, "setProgress", progress)
            state = snapshot(page)
            assert_prefix(state, mapping)
            require(state["activeId"] == placement["id"], "Media source/placement changed unexpectedly.")
            frame(420 if progress == 1 else 170)
            if placement["id"] == "B-001" and progress == 1:
                card.screenshot(path=str(output / "B-guide-start.png"), animations="disabled")
        if placement["id"] in {"B-001", "B-005", "B-010", "B-014", "B-019", "B-021", "B-024"}:
            durations[-1] += 550
            print(f"Captured assembly step {placement['step']}.", flush=True)
    require(len({image.size for image in frames}) == 1, "Capture layout shifted between animation frames.")
    gif = output / "B-guide-base-front.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)
    api(page, "setCursor", 20)
    api(page, "setProgress", 1)
    api(page, "setView", "assembly", "front")
    card.screenshot(path=str(output / "B-guide-front.png"), animations="disabled")
    with Image.open(gif) as image:
        require(image.n_frames == len(frames), "Saved GIF lost actual assembly frames.")
    return {"frames": len(frames), "duration_ms": sum(durations), "last_placement": "B-024",
            "source": "actual standalone viewer, deterministic insertion progress; not a physical simulation"}


def exercise(page, mapping):
    require(api(page, "mapping") == mapping, "Browser mapping differs from the verified JSON.")
    initial = snapshot(page)
    require(initial["cursor"] == 0 and initial["step"] == 0 and initial["activeId"] is None
            and initial["assemblyPoses"] == [], "Initial scene is not an empty table.")
    require(page.locator("#step-select").input_value() == "0", "Empty step selection was overwritten.")
    page.locator("#plate-select").select_option("B-black-01.3mf")
    page.locator("#plate-select").select_option("B-black-02.3mf")
    api(page, "setView", "plate", "top")
    label = page.locator('#plate-labels [aria-label="プレート内slot 3"]')
    label.scroll_into_view_if_needed()
    box = label.bounding_box()
    require(box is not None, "First base's physical-plate label is missing.")
    page.mouse.click(box["x"] + box["width"] / 2 + 45, box["y"] + box["height"] / 2 + 5)
    selected = snapshot(page)
    require(selected["selectedSlot"] == "B-black-02.3mf#3"
            and selected["candidateIds"] == ["B-001"], "Clicking the large base did not identify B-001.")
    require("191.8 × 79.8 × 11.4" in page.locator("#selected-size").inner_text(), "First base dimensions missing.")
    require("工程1" in page.locator("#target-list").inner_text(), "First base assembly step missing.")
    assert_framed(page, "plate")
    page.locator("#start-first").click()
    require(snapshot(page)["activeId"] == "B-001", "First-part action did not start step 1.")
    page.locator("#motion-progress").focus()
    page.keyboard.press("End")
    seated = snapshot(page)
    assert_prefix(seated, mapping)
    require(seated["progress"] == 1 and seated["activeSeated"] and seated["seatedCount"] == 1
            and seated["seatedIds"] == ["B-001"], "Keyboard motion End did not mark the first visual placement.")
    require(re.match(r"^1\s*/\s*150\b", page.locator("#cursor-value").inner_text()) is not None
            and "次は" not in page.locator("#action-title").inner_text(),
            "The first part is seated but its visible count/title still say it is next.")
    page.locator("#next").focus()
    page.keyboard.press("Enter")
    after_next = snapshot(page)
    require(after_next["completedIds"] == ["B-001"] and after_next["activeId"] == "B-002",
            "Keyboard Next omitted or duplicated the first placement.")
    page.locator("#previous").click()
    require(snapshot(page)["cursor"] == 0 and snapshot(page)["activeId"] == "B-001", "Previous did not restore the first preview.")
    print("Offline empty start, actual base click and first-step controls PASS.", flush=True)

    checks = page.evaluate("""() => {
      const data = window.BrickAssemblyGuide.mapping();
      const placementIndex = new Map(data.placements.map(part => [part.id, part]));
      const slotIndex = new Map(data.plates.flatMap(plate => plate.slots.map(slot => [slot.id, slot])));
      let slots = 0, placements = 0;
      for (const plate of data.plates) for (const slot of plate.slots) {
        const target = placementIndex.get(slot.suggested_placement), group = data.groups[slot.group];
        if (target.suggested_source.slot_id !== slot.id
            || JSON.stringify(group.placements) !== JSON.stringify(slot.candidate_placements)
            || !group.sources.some(source => source.slot_id === slot.id)) {
          throw new Error('Wrong slot direction: ' + slot.id);
        }
        slots++;
      }
      for (const part of data.placements) {
        const source = slotIndex.get(part.suggested_source.slot_id);
        if (source.suggested_placement !== part.id || !source.candidate_placements.includes(part.id)) {
          throw new Error('Wrong placement direction: ' + part.id);
        }
        placements++;
      }
      return { slots, placements };
    }""")
    require(checks == {"slots": 150, "placements": 150}, "Not all 150 mapping pairs were checked in the browser.")
    for plate in mapping["plates"]:
        page.locator("#plate-select").select_option(plate["file"])
        selected = snapshot(page)
        require(selected["selectedPlate"] == plate["file"] and selected["selectedSlotNumber"] == 1
                and page.locator("#slot-list [data-slot]").count() == len(plate["slots"]),
                "A plate selector did not expose all its actual slots.")
    placement_index = {row["id"]: row for row in mapping["placements"]}
    for group in mapping["groups"].values():
        source = group["sources"][0]
        api(page, "selectSlot", source["slot_id"])
        selected = snapshot(page)
        require(selected["selectedSlot"] == source["slot_id"]
                and selected["selectedPlacement"] == source["suggested_placement"]
                and selected["candidateIds"] == group["placements"]
                and selected["sourceSlots"] == [row["slot_id"] for row in group["sources"]],
                "An actual part/color group selection lost a source or destination.")
        identifier = group["placements"][-1]
        api(page, "selectPlacement", identifier)
        selected = snapshot(page)
        require(selected["selectedPlacement"] == identifier
                and selected["selectedSlot"] == placement_index[identifier]["suggested_source"]["slot_id"]
                and identifier in selected["candidateIds"], "Reverse selection did not reach its real source.")
    print("All 150 mapping pairs, 14 plate selectors and 23 part/color UI groups PASS.", flush=True)
    for number in range(1, 29):
        page.locator("#step-select").select_option(str(number))
        current = snapshot(page)
        require(current["cursor"] == mapping["steps"][number - 1]["first_index"]
                and not current["playing"], f"Step {number} navigation is inconsistent.")
        assert_prefix(current, mapping)
        assert_framed(page, "assembly")
    require(snapshot(page)["completedIds"] == [p["id"] for p in mapping["placements"]],
            "Final step is not exactly 150 placed parts.")
    print("All 28 step boundaries, accumulated placements and fitted cameras PASS.", flush=True)

    page.locator("#step-select").select_option("2")
    page.locator("#speed").select_option("700")
    page.locator("#play").click()
    wait_for_state(page, lambda state: state["progress"] > .1, "Playback did not advance.")
    page.locator("#play").click()
    paused = snapshot(page)
    page.wait_for_timeout(200)
    require(not snapshot(page)["playing"] and snapshot(page)["progress"] == paused["progress"],
            "Pause allowed assembly motion to continue.")
    page.locator("#play").click()
    page.locator("#step-select").select_option("6")
    moved = snapshot(page)
    page.wait_for_timeout(200)
    require(moved["cursor"] == 19 and not moved["playing"] and snapshot(page)["progress"] == 0,
            "Changing steps did not cancel playback.")
    assert_prefix(snapshot(page), mapping)

    page.locator("#step-select").select_option("3")
    page.locator("#replay-step").click()
    wait_for_state(page, lambda state: not state["playing"], "Step replay did not stop.")
    require(snapshot(page)["cursor"] == 10, "Step replay did not stop after exactly its own five parts.")
    assert_prefix(snapshot(page), mapping)
    page.locator("#step-select").select_option("7")
    page.locator("#speed").select_option("1500")
    started = time.monotonic()
    page.locator("#replay-step").click()
    keeper_end = wait_for_state(page, lambda state: not state["playing"],
                               "Keeper replay did not stop within 15 seconds.", timeout=15)
    keeper_seconds = time.monotonic() - started
    require(keeper_end["cursor"] == keeper_end["seatedCount"] == 24 and keeper_seconds <= 15,
            "Keeper replay did not seat exactly 24 pieces within 15 seconds.")
    assert_prefix(keeper_end, mapping)
    page.locator("#ghost").uncheck()
    for index in (19, 20):
        placement = mapping["placements"][index]
        api(page, "setCursor", index)
        for progress in (0, .14, .28, .55, 1):
            api(page, "setProgress", progress)
            current = snapshot(page)
            assert_prefix(current, mapping)
            pose = next(row for row in current["assemblyPoses"] if row["id"] == placement["id"])
            if progress >= .28:
                require(same_vector(pose["rotation"], [90, 0, 0]), "Front part did not rotate upright.")
            if progress == 1:
                require(same_vector(pose["position"], placement["position"]), "Front part missed its final slot.")
            assert_framed(page, "assembly")
        api(page, "setView", "assembly", "front")
        pixels = np.asarray(canvas_image(page, "assembly"))
        require(int(np.all(pixels > 240, axis=2).sum()) > 20
                and int(np.all(pixels < 120, axis=2).sum()) > 200, "Black body / white relief are not visible together.")
        api(page, "setView", "assembly", "iso")

    api(page, "selectSlot", "B-black-01.3mf#1")
    require(snapshot(page)["candidateIds"] == ["B-006", "B-015"], "Left-end copies were misrepresented as a left/right pair.")
    page.locator("#plate-isolate").check()
    for scene in ("plate", "assembly"):
        for view in ("iso", "front", "side", "top", "back", "bottom"):
            page.locator(f'.view-tools[data-scene="{scene}"] button[data-view="{view}"]').click()
            assert_framed(page, scene)
    plate = page.locator("#plate-canvas")
    before_rotation = hashlib.sha256(plate.screenshot()).hexdigest()
    plate.focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    require(hashlib.sha256(plate.screenshot()).hexdigest() != before_rotation, "Keyboard camera rotation did not change the view.")
    plate.hover(position={"x": 12, "y": 12})
    before_zoom = hashlib.sha256(canvas_image(page, "plate").tobytes()).hexdigest()
    page.mouse.wheel(0, -180)
    page.wait_for_timeout(120)
    require(hashlib.sha256(canvas_image(page, "plate").tobytes()).hexdigest() != before_zoom,
            "Wheel zoom did not change the view.")
    api(page, "setView", "plate", "iso")
    page.locator("#plate-isolate").uncheck()
    for width in (320, 768, 1024, 1440):
        page.set_viewport_size({"width": width, "height": 1100})
        page.wait_for_timeout(120)
        require(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"),
                f"Guide overflows horizontally at {width}px.")
        page.locator("#start-first").click()
        assert_framed(page, "plate")
        assert_framed(page, "assembly")
        page.locator("#next").focus()
        page.keyboard.press("Enter")
        assert_prefix(snapshot(page), mapping)
    for _ in range(3):
        page.locator("#restart").click()
        empty = snapshot(page)
        require(empty["completedIds"] == [] and empty["assemblyPoses"] == []
                and empty["activeId"] is None and empty["step"] == 0 and not empty["playing"],
                "Restart is not a stable, empty assembly state.")
    print("Playback, 90-degree fronts, six views, keyboard and responsive controls PASS.", flush=True)
    return {"mapping_slots_checked": 150, "mapping_placements_checked": 150,
            "plate_ui_selections": 14, "part_color_groups_ui_checked": 23,
            "slot_ui_selections": 23, "placement_ui_selections": 23,
            "steps_navigated": 28, "responsive_widths": [320, 768, 1024, 1440],
            "empty_start_and_restart": True, "large_base_canvas_click": True,
            "seated_count_at_progress_one": True,
            "prefix_preserved": True, "play_pause_step_replay": True, "step_navigation_stops_play": True,
            "play_button_matches_state": True,
            "step_7_replay_stops_at_24": True, "step_7_replay_max_seconds": 15,
            "step_7_replay_elapsed_seconds": round(keeper_seconds, 3),
            "front_rotation_degrees": 90, "black_and_white_relief_visible": True,
            "views": ["iso", "front", "side", "top", "back", "bottom"],
            "keyboard_selection_and_rotation": True, "wheel_zoom": True, "camera_framing": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, default=ROOT / "guide/index.html")
    parser.add_argument("--capture", action="store_true", help="Write README PNG/GIF frames from this actual viewer.")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    entry = args.entry.resolve()
    mapping = json.loads(entry.with_suffix(".mapping.json").read_text(encoding="utf-8"))
    verify_mapping(mapping)
    verify_embedded(mapping, entry)
    html_contract = verify_file(entry)
    network, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1100},
                                          offline=True, service_workers="block", device_scale_factor=1)

            def requested(request):
                if urlsplit(request.url).scheme in {"http", "https", "ws", "wss"}:
                    network.append(request.url)

            def route_request(route):
                if urlsplit(route.request.url).scheme in {"http", "https", "ws", "wss"}:
                    route.abort()
                else:
                    route.continue_()

            context.on("request", requested)
            context.route("**/*", route_request)
            page = context.new_page()
            page.set_default_timeout(30000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("websocket", lambda socket: network.append(socket.url))
            page.goto(entry.as_uri(), wait_until="load")
            page.locator('#guide-app:not([data-ready="false"])').wait_for(state="attached", timeout=180000)
            require(page.locator("#guide-app").get_attribute("data-ready") == "true",
                    f"Guide failed to initialize: {page.locator('#guide-error').inner_text()}")
            checks = exercise(page, mapping)
            media = capture_media(page, mapping) if args.capture else None
            require(not network, "Offline viewer attempted an external network request.")
            require(not errors, f"Browser errors: {errors}")
            report = {
                "status": "PASS", "entry": "guide/index.html", "entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest(),
                "canonical_guide_sha256": canonical_guide_hash(entry),
                "navigation_scheme": urlsplit(page.url).scheme, "browser_network_offline": True,
                "external_network_requests": len(network), "console_or_page_errors": len(errors),
                "browser": browser.version, "playwright": version("playwright"), "pillow": version("Pillow"),
                "document": html_contract, "checks": checks,
                "physical_fit_strength_stability": "NOT_TESTED", "sliced": False,
            }
            if media:
                report["media"] = media
                report["media_files"] = {
                    f"docs/images/{name}": hashlib.sha256((ROOT / "docs/images" / name).read_bytes()).hexdigest()
                    for name in ("B-guide-start.png", "B-guide-front.png", "B-guide-base-front.gif")
                }
            if args.write_report:
                (ROOT / "verification/guide-browser.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
