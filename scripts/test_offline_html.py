#!/usr/bin/env python3
"""Focused regression tests for the private offline document contract."""

import unittest

from verify_offline_html import verify_document


PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'">
<style>body { margin: 0; }</style></head><body>
<script>window.example = true;</script></body></html>"""


class OfflineDocumentTests(unittest.TestCase):
    def test_embedded_document(self):
        self.assertEqual(verify_document(PAGE)["external_active_resources"], 0)

    def test_runtime_must_be_classic_and_embedded(self):
        for tag in ('<script src="runtime.js">', '<script type="module">'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                verify_document(PAGE.replace("<script>", tag))

    def test_external_resources_are_rejected(self):
        for tag in (
            '<link rel="stylesheet" href="style.css">',
            '<img src="https://example.invalid/pixel">',
            '<video poster="preview.png">',
            '<iframe src="other.html"></iframe>',
            '<meta http-equiv="refresh" content="0;url=https://example.invalid">',
            '<style>@import "extra.css";</style>',
            '<style>body { background: url(extra.png); }</style>',
        ):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                verify_document(PAGE.replace("</head>", tag + "</head>"))

    def test_network_connections_must_be_disabled(self):
        for policy in ("", "connect-src 'self'", "connect-src 'none' https:"):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                verify_document(PAGE.replace("connect-src 'none'", policy))

    def test_embedded_images_and_normal_document_links_are_allowed(self):
        page = PAGE.replace("</body>", '<img src="data:image/png;base64,AA==">'
                            '<a href="../docs/GUIDE.md">Help</a></body>')
        self.assertEqual(verify_document(page)["inline_runtime_scripts"], 1)


if __name__ == "__main__":
    unittest.main()
