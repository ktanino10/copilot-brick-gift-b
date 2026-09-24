import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_photo_log


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


if __name__ == "__main__":
    unittest.main()
