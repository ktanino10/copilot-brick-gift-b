#!/usr/bin/env python3
"""Read-only guard for the explicitly authorized public recipient repository."""

import json
import subprocess
from pathlib import Path


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
            raise SystemExit("STOP: origin does not point exclusively to the recipient kit repository.")

    policy = json.loads((Path(__file__).resolve().parents[1] / "publication/policy.json").read_text())
    if policy["repository"] != REPOSITORY or policy["repository_visibility"] != "public" or policy["pages_enabled"] is not True:
        raise SystemExit("STOP: the explicit publication policy does not authorize this target.")
    metadata = json.loads(
        output("gh", "api", "--hostname", "github.com", f"repos/{REPOSITORY}")
    )
    expected = {
        "full_name": REPOSITORY,
        "private": False,
        "visibility": "public",
        "has_pages": True,
        "fork": False,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise SystemExit(f"STOP: repository setting {key} is not {value!r}.")
    print(json.dumps(expected, sort_keys=True))
    print("Authorized public recipient target confirmed. This check changes no settings.")


if __name__ == "__main__":
    main()
