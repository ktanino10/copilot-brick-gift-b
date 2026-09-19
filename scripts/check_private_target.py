#!/usr/bin/env python3
"""Read-only guard to run immediately before every upload."""

import json
import subprocess


REPOSITORY = "ktanino10/copilot-brick-gift-b"
ALLOWED_REMOTES = {
    f"https://github.com/{REPOSITORY}.git",
    f"git@github.com:{REPOSITORY}.git",
    f"ssh://git@github.com/{REPOSITORY}.git",
}


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    for direction in ([], ["--push"]):
        urls = output("git", "remote", "get-url", *direction, "--all", "origin")
        if not urls or any(url not in ALLOWED_REMOTES for url in urls.splitlines()):
            raise SystemExit("STOP: origin does not point exclusively to the private kit repository.")

    metadata = json.loads(
        output("gh", "api", "--hostname", "github.com", f"repos/{REPOSITORY}")
    )
    expected = {
        "full_name": REPOSITORY,
        "private": True,
        "visibility": "private",
        "has_pages": False,
        "fork": False,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise SystemExit(f"STOP: repository setting {key} is not {value!r}.")
    print(json.dumps(expected, sort_keys=True))
    print("Private target confirmed. This check does not upload or change any settings.")


if __name__ == "__main__":
    main()
