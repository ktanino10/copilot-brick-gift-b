from pathlib import Path
import tempfile
import unittest

from build_recipient_site import SiteBuilder
from verify_recipient_site import Document
from user_video import USER_VIDEO_EMBED_URL, USER_VIDEO_FRAME_ID, USER_VIDEO_TITLE


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

    def test_only_the_explicit_public_video_frame_is_permitted(self):
        markup = (f'<iframe id="{USER_VIDEO_FRAME_ID}" name="{USER_VIDEO_FRAME_ID}" '
                  f'src="{USER_VIDEO_EMBED_URL}" title="{USER_VIDEO_TITLE}" '
                  'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>')
        document = Document(allow_user_video=True)
        document.feed(markup)
        self.assertEqual(len(document.frames), 1)
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
