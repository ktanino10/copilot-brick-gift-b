from pathlib import Path
import tempfile
import unittest

from build_recipient_site import SiteBuilder
from build_photo_log import CLI_ARRANGEMENT_ANCHOR, PROGRESS_ANCHOR
from verify_recipient_site import Document
from user_video import CLEANING_VIDEO, PRINTING_VIDEO, USER_VIDEOS


class RecipientSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.site = SiteBuilder(Path(self.temp.name), "a" * 40)

    def tearDown(self):
        self.temp.cleanup()

    def test_reader_links_stay_under_the_project_prefix(self):
        self.assertEqual(
            self.site.url("BUILD-LOG.md", "docs/PRINTING.md", "docs/PRINTING.html"),
            "BUILD-LOG.html",
        )
        self.assertEqual(
            self.site.url("../README.md", "docs/PRINTING.md", "docs/PRINTING.html"), "../index.html"
        )

    def test_native_and_history_are_not_active_site_assets(self):
        for name in ("source/native/B.FCStd", "verification/native.json", ".private/notes.txt",
                     "revisions/4.0-B-personal-kit.2/nameplate/plate.stl"):
            self.assertFalse(self.site.allowed_asset(name))
            with self.assertRaisesRegex(ValueError, "Unapproved"):
                self.site.asset(name)

    def test_remote_or_outside_images_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            self.site.url("https://example.invalid/photo.jpg", "docs/BUILD-LOG.md", "docs/BUILD-LOG.html", active=True)
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.site.url("../../outside.jpg", "docs/BUILD-LOG.md", "docs/BUILD-LOG.html", active=True)

    def test_cli_photo_is_additive_and_uses_project_relative_links(self):
        self.site.build()
        log = Document(allow_user_video=True)
        log.feed((self.site.output / "docs/BUILD-LOG.html").read_text())
        self.assertEqual(len(log.images), 25)
        self.assertIn("images/build-log-2026-09-25/finished-portrait.jpg", log.images)
        self.assertIn("images/build-log-2026-09-30/cli-style-arrangement.jpg", log.images)
        self.assertTrue({PROGRESS_ANCHOR, CLI_ARRANGEMENT_ANCHOR, "progress-2026-09-24"} <= log.ids)
        homepage = Document()
        homepage.feed((self.site.output / "index.html").read_text())
        self.assertIn(f"docs/BUILD-LOG.html#{CLI_ARRANGEMENT_ANCHOR}", homepage.links)
        self.assertIn("docs/images/build-log-2026-09-25/finished-portrait.jpg", homepage.images)
        self.assertNotIn("docs/images/build-log-2026-09-30/original.png", self.site.files)
        self.assertFalse(self.site.allowed_asset("docs/images/build-log-2026-09-30/unapproved.jpg"))

    def test_only_the_explicit_public_video_frame_is_permitted(self):
        markup = "".join(
            f'<iframe id="{item["frame_id"]}" name="{item["frame_id"]}" '
            f'src="{item["embed_url"]}" title="{item["title"]}" '
            'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>'
            for item in USER_VIDEOS
        )
        document = Document(allow_user_video=True)
        document.feed(markup)
        self.assertEqual([frame["src"] for frame in document.frames],
                         [PRINTING_VIDEO["embed_url"], CLEANING_VIDEO["embed_url"]])
        with self.assertRaisesRegex(ValueError, "authorized"):
            Document().feed(markup)
        for invalid in (
            markup.replace("playsinline=1", "autoplay=1"),
            markup.replace("youtube-nocookie.com", "example.invalid"),
            markup.replace("strict-origin-when-cross-origin", "no-referrer"),
        ):
            with self.assertRaisesRegex(ValueError, "authorized"):
                Document(allow_user_video=True).feed(invalid)


if __name__ == "__main__":
    unittest.main()
