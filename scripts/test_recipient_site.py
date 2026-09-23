from pathlib import Path
import tempfile
import unittest

from build_recipient_site import SiteBuilder


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


if __name__ == "__main__":
    unittest.main()
