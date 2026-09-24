import unittest

from build_log_navigation import ANCHOR, NAVIGATION, PREVIOUS_NAVIGATION, add_navigation, base_document


class BuildLogNavigationTests(unittest.TestCase):
    def test_roundtrip_preserves_every_original_byte(self):
        original = "<html>\n" + ANCHOR + "\n<canvas></canvas>\n</html>\n"
        linked = add_navigation(original)
        self.assertEqual(base_document(linked), original)
        self.assertEqual(add_navigation(linked), linked)

    def test_changed_or_duplicated_navigation_is_rejected(self):
        original = ANCHOR + "\n"
        with self.assertRaisesRegex(ValueError, "duplicated"):
            base_document(NAVIGATION + NAVIGATION + original)
        with self.assertRaisesRegex(ValueError, "unexpectedly"):
            base_document(add_navigation(original).replace("BUILD-LOG.html", "different.html"))

    def test_existing_geometry_changes_remain_visible(self):
        original = ANCHOR + '<script>const shape = "original";</script>'
        changed = add_navigation(original).replace('"original"', '"changed"')
        self.assertNotEqual(base_document(changed), original)

    def test_previous_fixed_navigation_migrates_without_renderer_changes(self):
        original = "<html>\n" + ANCHOR + "\n<canvas></canvas>\n</html>\n"
        previous = original.replace(ANCHOR, PREVIOUS_NAVIGATION + ANCHOR)
        self.assertEqual(base_document(previous), original)
        self.assertEqual(add_navigation(previous), add_navigation(original))
        with self.assertRaisesRegex(ValueError, "duplicated"):
            base_document(PREVIOUS_NAVIGATION + NAVIGATION + original)


if __name__ == "__main__":
    unittest.main()
