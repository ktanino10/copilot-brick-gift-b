import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_photo_log
from verify_build_log import JournalDocument, USER_VIDEO_PAGE_URL, USER_VIDEO_URL, verify_user_video_link


class ApprovedPhotoBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / "docs/images/test-batch"
        self.directory.mkdir(parents=True)
        self.photo = self.directory / "example.jpg"
        self.photo.write_bytes(b"byte-preservation fixture; image decoding is checked by the journal verifier")
        manifest = {"photos": [{
            "id": "example", "path": "example.jpg",
            "sha256": hashlib.sha256(self.photo.read_bytes()).hexdigest(),
        }]}
        data = json.dumps(manifest).encode()
        (self.directory / "manifest.json").write_bytes(data)
        self.batch = {"directory": "docs/images/test-batch", "photo_count": 1,
                      "manifest_sha256": hashlib.sha256(data).hexdigest()}

    def tearDown(self):
        self.temp.cleanup()

    def read(self):
        with patch.object(build_photo_log, "ROOT", self.root), patch.object(
            build_photo_log, "PHOTO_BATCHES", (self.batch,)
        ):
            return build_photo_log.approved_photos()

    def test_only_the_approved_exact_bytes_are_listed(self):
        self.assertEqual(set(self.read()), {"images/test-batch/example.jpg"})

    def test_reprocessing_a_photo_is_not_silently_accepted(self):
        self.photo.write_bytes(b"different image")
        with self.assertRaisesRegex(ValueError, "reprocess"):
            self.read()

    def test_modified_manifest_is_rejected(self):
        (self.directory / "manifest.json").write_text('{"photos":[]}')
        with self.assertRaisesRegex(ValueError, "manifest was changed"):
            self.read()

    def test_raw_or_audit_files_are_not_allowed_in_the_batch(self):
        (self.directory / "source-map.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Only approved photos"):
            self.read()


class UserVideoLinkTests(unittest.TestCase):
    def document(self, link):
        document = JournalDocument()
        document.feed(link)
        return document

    def test_exact_safe_user_link_is_allowed(self):
        verify_user_video_link(self.document(
            f'<a href="{USER_VIDEO_PAGE_URL}" target="_blank" rel="noopener noreferrer">Web player</a>'
            f'<a href="{USER_VIDEO_URL}" target="_blank" rel="noopener noreferrer">YouTube</a>'
        ))

    def test_missing_safety_or_changed_tracking_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "safe new-tab"):
            verify_user_video_link(self.document(
                f'<a href="{USER_VIDEO_PAGE_URL}" target="_blank" rel="noopener noreferrer">Web player</a>'
                f'<a href="{USER_VIDEO_URL}" target="_blank">YouTube</a>'
            ))
        with self.assertRaisesRegex(ValueError, "exact"):
            verify_user_video_link(self.document(
                f'<a href="{USER_VIDEO_PAGE_URL}" target="_blank" rel="noopener noreferrer">Web player</a>'
                f'<a href="{USER_VIDEO_URL}?tracking=1" target="_blank" rel="noopener noreferrer">YouTube</a>'
            ))

    def test_automatic_video_embed_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "passive"):
            self.document('<iframe src="https://www.youtube.com/embed/Lc_enNE3nng"></iframe>')


if __name__ == "__main__":
    unittest.main()
