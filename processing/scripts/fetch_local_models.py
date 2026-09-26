"""Downloads the trained models from their public GitHub Releases into a
local directory laid out like the goodgorithm-models R2 bucket, for
processing/ to load via LOCAL_MODELS_DIR (see infra/model_store.py's
LocalDirModelStore). No credentials needed.

Usage (from processing/):
    uv run python scripts/fetch_local_models.py [--dir ../models] [--version quality-classifier=v2 ...]

For each model prefix, picks the newest `<prefix>-v<N>` release unless
--version pins one, downloads every asset into <dir>/<prefix>/<version>/,
and writes <dir>/<prefix>/latest.json. Files already present are skipped.

A release is created when a version is promoted to production, so the
newest release is normally the live one -- but after a rollback it isn't.
Pin with --version to match production's /health `models` block when that
matters.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

REPO = "goodgorithm/goodgorithm"
PREFIXES = ("political-classifier", "political-centroid", "quality-classifier")
TIMEOUT_SECONDS = 60


def list_releases() -> list[dict]:
    releases: list[dict] = []
    page = 1
    while True:
        response = requests.get(
            f"https://api.github.com/repos/{REPO}/releases",
            params={"per_page": 100, "page": page},
            headers={"Accept": "application/vnd.github+json"},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            return releases
        releases.extend(batch)
        page += 1


def select_release(releases: list[dict], prefix: str, pinned_version: str | None) -> dict:
    """The release for `prefix`: the pinned version if given, else the
    highest v<N>. Matches the tag exactly (`<prefix>-v<N>`), so one prefix
    can't pick up another's release."""
    pattern = re.compile(rf"^{re.escape(prefix)}-(v(\d+))$")
    candidates = []
    for release in releases:
        match = pattern.match(release.get("tag_name", ""))
        if match:
            candidates.append((int(match.group(2)), match.group(1), release))
    if pinned_version is not None:
        for _, version, release in candidates:
            if version == pinned_version:
                return release
        raise SystemExit(f"no release {prefix}-{pinned_version}")
    if not candidates:
        raise SystemExit(f"no releases found for {prefix}")
    return max(candidates, key=lambda c: c[0])[2]


def version_of(release: dict, prefix: str) -> str:
    return release["tag_name"][len(prefix) + 1 :]


def fetch(root: Path, prefix: str, release: dict) -> None:
    version = version_of(release, prefix)
    version_dir = root / prefix / version
    version_dir.mkdir(parents=True, exist_ok=True)
    for asset in release["assets"]:
        target = version_dir / asset["name"]
        if target.exists():
            print(f"  {prefix}/{version}/{asset['name']}: present, skipped")
            continue
        response = requests.get(asset["browser_download_url"], timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        partial = target.with_suffix(target.suffix + ".partial")
        partial.write_bytes(response.content)
        partial.rename(target)
        print(f"  {prefix}/{version}/{asset['name']}: downloaded ({len(response.content)} bytes)")
    (root / prefix / "latest.json").write_text(json.dumps({"version": version}) + "\n")
    print(f"  {prefix}/latest.json -> {version}")


def parse_pins(values: list[str]) -> dict[str, str]:
    pins = {}
    for value in values:
        prefix, sep, version = value.partition("=")
        if not sep or prefix not in PREFIXES or not re.fullmatch(r"v\d+", version):
            raise SystemExit(f"bad --version {value!r}: expected <prefix>=v<N>, prefix one of {', '.join(PREFIXES)}")
        pins[prefix] = version
    return pins


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default="../models", help="target directory (default: ../models, the repo-root models/)")
    parser.add_argument("--version", action="append", default=[], help="pin a version, e.g. quality-classifier=v1")
    args = parser.parse_args(argv)

    pins = parse_pins(args.version)
    root = Path(args.dir)
    releases = list_releases()
    for prefix in PREFIXES:
        print(prefix)
        fetch(root, prefix, select_release(releases, prefix, pins.get(prefix)))
    print(f"done -- set LOCAL_MODELS_DIR={root.resolve()} in processing/.env")


if __name__ == "__main__":
    main(sys.argv[1:])
