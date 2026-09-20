#!/usr/bin/env python3
"""Check the standalone document's active resources without opening a server."""

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re


class StandaloneDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.csp = None
        self.charset = None
        self.inline_scripts = 0
        self.style_depth = 0
        self.styles = []
        self.language = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"iframe", "object", "embed", "form", "base"}:
            raise ValueError(f"Standalone guide must not contain an active {tag} element.")
        if tag == "html":
            self.language = attrs.get("lang")
        if tag == "meta":
            if "charset" in attrs:
                self.charset = attrs["charset"].lower()
            directive = attrs.get("http-equiv", "").lower()
            if directive == "refresh":
                raise ValueError("Standalone guide must not redirect or refresh automatically.")
            if directive == "content-security-policy":
                if self.csp is not None:
                    raise ValueError("Standalone guide has duplicate content security policies.")
                self.csp = attrs.get("content", "")
        if tag == "script":
            if "src" in attrs or attrs.get("type", "").lower() == "module":
                raise ValueError("The runtime must be inline classic JavaScript, not a URL or module.")
            if attrs.get("type", "").lower() not in {"application/json", "application/ld+json"}:
                self.inline_scripts += 1
        if tag == "link" and "href" in attrs:
            raise ValueError("A standalone guide must inline styles, icons and fonts.")
        for attr in ("src", "srcset", "poster", "background", "xlink:href"):
            if attr in attrs and not attrs[attr].startswith(("data:", "#")):
                raise ValueError(f"Nonembedded resource: {tag}/{attr}.")
        if "style" in attrs:
            self.styles.append(attrs["style"])
        if tag == "style":
            self.style_depth += 1

    def handle_endtag(self, tag):
        if tag == "style":
            self.style_depth -= 1

    def handle_data(self, data):
        if self.style_depth:
            self.styles.append(data)

    def verify(self):
        if self.charset != "utf-8" or not self.language:
            raise ValueError("Standalone guide must declare UTF-8 and its document language.")
        if not self.inline_scripts:
            raise ValueError("Standalone guide is missing its embedded runtime.")
        directives = {}
        for directive in (self.csp or "").split(";"):
            words = directive.split()
            if words:
                directives[words[0]] = words[1:]
        if directives.get("connect-src") != ["'none'"]:
            raise ValueError("Standalone guide must explicitly use connect-src 'none'.")
        for style in self.styles:
            if re.search(r"@import\b", style, flags=re.IGNORECASE):
                raise ValueError("Standalone guide must not import external CSS.")
            for url in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", style, flags=re.IGNORECASE):
                if not url.startswith(("data:", "#")):
                    raise ValueError("Standalone guide must not load an external CSS resource.")
        return {
            "inline_runtime_scripts": self.inline_scripts,
            "connect_src": "'none'",
            "external_active_resources": 0,
            "charset": self.charset,
            "language": self.language,
        }


def verify_document(text):
    document = StandaloneDocument()
    document.feed(text)
    document.close()
    return document.verify()


def verify_file(path):
    return verify_document(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[1] / "guide/index.html")
    args = parser.parse_args()
    print(json.dumps(verify_file(args.entry), sort_keys=True))


if __name__ == "__main__":
    main()
