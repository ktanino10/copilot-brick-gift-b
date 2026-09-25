"""The two exact user-authorized process videos, in the requested explanation order."""

PUBLIC_JOURNAL_URL = "https://ktanino10.github.io/copilot-brick-gift-b/docs/BUILD-LOG.html"
USER_VIDEO_EMBED_ORIGIN = "https://www.youtube-nocookie.com"


def video(video_id, anchor, frame_id, placeholder_id, title):
    return {
        "video_id": video_id, "anchor": anchor, "frame_id": frame_id, "title": title,
        "url": "https://youtu.be/" + video_id, "page_url": PUBLIC_JOURNAL_URL + "#" + anchor,
        "embed_url": USER_VIDEO_EMBED_ORIGIN + "/embed/" + video_id + "?playsinline=1",
        "placeholder": f'<div id="{placeholder_id}"></div>', "placeholder_id": placeholder_id,
    }


PRINTING_VIDEO = video(
    "sinN3dKGwRg", "printing-video-2026-09-25", "printing-video-frame", "printing-video-player",
    "AIでLEGO風ブロックを設計して3Dプリント｜GitHub Copilot × FreeCAD × Blender",
)
CLEANING_VIDEO = video(
    "Lc_enNE3nng", "post-processing-ultrasonic-2026-09-25", "user-video-frame", "user-video-player",
    "3Dプリント後のパーツを超音波洗浄｜Ultrasonic Cleaning of 3D-Printed Parts",
)
USER_VIDEOS = (PRINTING_VIDEO, CLEANING_VIDEO)
ONLINE_VIDEO_LINKS = tuple(link for item in USER_VIDEOS for link in (item["page_url"], item["url"]))
