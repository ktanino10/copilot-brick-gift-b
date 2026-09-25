"""Observe both authorized inline players using their actual controls; never download media."""

import argparse
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error as BrowserError, TimeoutError as BrowserTimeout, sync_playwright

from user_video import PRINTING_VIDEO, USER_VIDEOS


def player_state(frame):
    try:
        return frame.evaluate("""() => {
      const video = document.querySelector('video');
      const player = document.querySelector('#movie_player');
      const data = typeof player?.getVideoData === 'function' ? player.getVideoData() : null;
      const error = document.querySelector('.ytp-error-content-wrap,ytm-player-error-message-renderer,[role="alert"]');
      const playSelector = ['.ytmCuedOverlayPlayButton', '.ytp-large-play-button', '.ytp-play-button',
        'button[aria-label="Play video"]', 'button[aria-label="Play"]', 'button[aria-label="再生"]'].find(selector => {
          const button = document.querySelector(selector);
          return button && button.getClientRects().length && !button.disabled;
        }) || null;
      return {
        playerDetected: Boolean(player), videoId: data?.video_id ?? null,
        advertisement: Boolean(player?.classList.contains('ad-showing')),
        playButton: Boolean(playSelector), playSelector,
        visibleControls: [...document.querySelectorAll('button,[role="button"]')]
          .filter(button => button.getClientRects().length)
          .map(button => ({
            label: button.getAttribute('aria-label') || button.getAttribute('title') || button.textContent.trim(),
            className: String(button.className)
          })).slice(0, 20),
        errorText: error?.innerText?.trim() || '',
        video: video ? {
          currentTime: video.currentTime, paused: video.paused,
          readyState: video.readyState, ended: video.ended
        } : null,
        message: document.body?.innerText?.trim().slice(0, 600) || ''
      };
    }""")
    except BrowserError as error:
        if "Execution context was destroyed" not in str(error):
            raise
        return {"playerDetected": False, "playButton": False, "errorText": "", "video": None,
                "message": "Player frame navigated during this observation; retrying within the bounded wait."}


def observe_video(page, item):
    report = {
        "video_id": item["video_id"], "iframe_src": item["embed_url"],
        "playback_status": "NOT_CONFIRMED", "play_attempted": False,
    }
    iframe = page.locator("#" + item["frame_id"])
    iframe.wait_for(state="visible", timeout=30000)
    iframe.scroll_into_view_if_needed()
    if iframe.get_attribute("src") != item["embed_url"]:
        raise ValueError("The live page embeds a different video or autoplay parameters.")
    if iframe.get_attribute("referrerpolicy") != "strict-origin-when-cross-origin":
        raise ValueError("The live iframe uses an incompatible referrer policy.")
    report["iframe_visible"] = True
    frame = iframe.element_handle().content_frame()
    if frame is None:
        raise ValueError("The visible iframe has no browser frame.")
    deadline = time.monotonic() + 25
    observed = None
    while time.monotonic() < deadline:
        observed = player_state(frame)
        if observed["errorText"] or observed["playButton"]:
            break
        page.wait_for_timeout(250)
    report["before_play"] = observed
    if observed and observed["video"] and not observed["video"]["paused"] and observed["video"]["currentTime"] > .1:
        raise ValueError("Video playback started without a user gesture.")
    if observed and observed["playButton"] and not observed["errorText"]:
        try:
            frame.locator(observed["playSelector"]).first.click(timeout=5000)
            report["play_attempted"] = True
        except BrowserTimeout:
            report["playback_status"] = "PLAY_CONTROL_NOT_ACTIONABLE"
        if report["play_attempted"]:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                observed = player_state(frame)
                if observed["errorText"]:
                    report["playback_status"] = "YOUTUBE_PLAYER_ERROR"
                    break
                video = observed["video"]
                if (video and video["currentTime"] >= .5 and not video["paused"] and video["readyState"] >= 2
                        and observed.get("videoId") == item["video_id"] and not observed.get("advertisement")):
                    report["playback_status"] = "PLAYING_CONFIRMED"
                    break
                page.wait_for_timeout(250)
    elif observed and observed["errorText"]:
        report["playback_status"] = "YOUTUBE_PLAYER_ERROR"
    else:
        report["playback_status"] = "YOUTUBE_PLAYER_UI_UNAVAILABLE"
    report["observed_result"] = observed
    if report["playback_status"] == "PLAYING_CONFIRMED":
        pause = frame.get_by_role("button", name=re.compile(r"^(Pause|一時停止)"))
        if pause.count() and pause.first.is_visible():
            pause.first.click(timeout=5000)
            report["pause_method"] = "visible_player_button"
        else:
            frame.evaluate("() => document.querySelector('video')?.pause()")
            report["pause_method"] = "media_element_cleanup_not_UI_validation"
        deadline = time.monotonic() + 3
        paused = False
        while time.monotonic() < deadline:
            state = player_state(frame)
            paused = bool(state["video"] and state["video"]["paused"])
            if paused:
                break
            page.wait_for_timeout(100)
        report["paused_after_observation"] = paused
        if not report["paused_after_observation"]:
            frame.evaluate("() => document.querySelector('video')?.pause()")
            report["cleanup_pause_required"] = True
    report["limitation"] = (
        None if report["playback_status"] == "PLAYING_CONFIRMED"
        else "Playback was not confirmed; inspect the exact player message. No sign-in, consent or restriction bypass was attempted."
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=PRINTING_VIDEO["page_url"])
    parser.add_argument("--expected-commit")
    parser.add_argument("--report", type=Path, default=Path("build/youtube-player.json"))
    args = parser.parse_args()
    target = urlsplit(args.url)
    if target.scheme != "https" or target.netloc != "ktanino10.github.io" or target.path != "/copilot-brick-gift-b/docs/BUILD-LOG.html":
        raise ValueError("Only the authorized public recipient journal is in scope.")
    report = {"url": args.url, "downloaded_or_rehosted": False}
    popups = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        page = context.new_page()
        page.on("popup", lambda popup: popups.append(popup.url))
        referrers = {item["video_id"]: [] for item in USER_VIDEOS}

        def record_request(request):
            for item in USER_VIDEOS:
                if request.url == item["embed_url"]:
                    referrers[item["video_id"]].append(request.headers.get("referer", ""))

        page.on("request", record_request)
        response = page.goto(args.url, wait_until="domcontentloaded", timeout=120000)
        if response is None or response.status != 200:
            raise ValueError("The live journal did not load.")
        if args.expected_commit and args.expected_commit not in page.content():
            raise ValueError("The live page has not reached the expected deployment.")
        report["videos"] = [observe_video(page, item) for item in USER_VIDEOS]
        report["referrer_headers_observed"] = referrers
        report["new_tabs"] = len(popups)
        if popups:
            raise ValueError("The primary playback attempt unexpectedly opened a new tab.")
        page.set_viewport_size({"width": 390, "height": 844})
        for item in USER_VIDEOS:
            iframe = page.locator("#" + item["frame_id"])
            iframe.scroll_into_view_if_needed()
            box = iframe.bounding_box()
            if box is None or box["width"] > 390 or abs(box["width"] / box["height"] - 16 / 9) > .01:
                raise ValueError("A live player does not fit the mobile page.")
        if not page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"):
            raise ValueError("The live video page overflows horizontally.")
        report["mobile_frame_16_by_9"] = True
        report["browser_version"] = browser.version
        report["site_embed_status"] = "PASS"
        report["all_video_playback_confirmed"] = all(
            item["playback_status"] == "PLAYING_CONFIRMED" for item in report["videos"]
        )
        report["all_video_pause_buttons_confirmed"] = all(
            item.get("pause_method") == "visible_player_button" and item.get("paused_after_observation")
            for item in report["videos"]
        )
        browser.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
