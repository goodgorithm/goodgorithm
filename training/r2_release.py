#!/usr/bin/env python3
"""Inspect, promote, or roll back the live version of a trained model in R2.

Flips `<prefix>/latest.json` (what processing/'s model-loading code
actually reads) without needing to re-run the training notebook. Useful for:

  - promoting a version the notebook already uploaded with
    PUBLISH_AS_LATEST=False (the notebook's default -- publishing artifacts
    and promoting to production are deliberately separate steps)
  - rolling back to a previously-published version if a new one turns out
    to be worse in production than eval numbers suggested
  - checking what's currently live, and what versions exist at all

Generalized across model types (sentiment, category) rather than forked per
model -- see MODEL_REGISTRY below. The coupling to any one model's naming
was always shallow: `current`/`list`/`publish`/`create_github_release`
never had model-specific logic in their bodies, just a prefix and an
artifact list. CLAUDE.md's own stated principle for this file: "extend
this shape to a new integration point before inventing a different one."

`publish` also mirrors the version's artifacts to a public GitHub Release
(`<prefix>-<version>`) -- goodgorithm-models is a private R2 bucket (no
r2.dev/custom domain configured, confirmed 2026-08-12), so without this
the "we open-source model weights" claim on the Mission/Algorithm wiki
pages wasn't actually true: the weights existed, but nobody outside the
project could download them.
Making the live version public is now a required part of promoting it,
not a separate/optional step.
Requires the `gh` CLI, authenticated, with access to goodgorithm/goodgorithm.

Usage:
    uv run python r2_release.py --model sentiment current
    uv run python r2_release.py --model sentiment list
    uv run python r2_release.py --model sentiment publish <version>
    uv run python r2_release.py --model category current
    uv run python r2_release.py --model category list
    uv run python r2_release.py --model category publish <version>

Requires the same R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY /
R2_BUCKET_NAME env vars processing/ uses -- see .env.example in the repo
root. Mirrors processing/src/model_store.py's registry layout exactly:
<prefix>/<version>/{artifacts...}, plus a single mutable
<prefix>/latest.json pointer, per model type.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3

GITHUB_REPO = "goodgorithm/goodgorithm"

# Add a new model type here, not a new script -- see module docstring.
MODEL_REGISTRY = {
    "sentiment": {
        "prefix": "sentiment-cnn",
        "artifacts": ["model.onnx", "vocab.json", "config.json"],
    },
    "category": {
        "prefix": "category-classifier",
        "artifacts": ["model.onnx", "config.json"],
    },
}

_REQUIRED_ENV = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"]


def _client():
    missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"missing required env vars: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _bucket() -> str:
    return os.environ["R2_BUCKET_NAME"]


def current(client, prefix: str) -> str | None:
    try:
        body = client.get_object(Bucket=_bucket(), Key=f"{prefix}/latest.json")["Body"].read()
    except client.exceptions.NoSuchKey:
        return None
    return json.loads(body)["version"]


def list_versions(client, prefix: str) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    versions: set[str] = set()
    for page in paginator.paginate(Bucket=_bucket(), Prefix=f"{prefix}/", Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            name = entry["Prefix"][len(f"{prefix}/") :].rstrip("/")
            if name:
                versions.add(name)
    return sorted(versions)


def _release_tag(prefix: str, version: str) -> str:
    return f"{prefix}-{version}"


def _release_exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", GITHUB_REPO],
        capture_output=True,
    )
    return result.returncode == 0


def create_github_release(client, prefix: str, artifacts: list[str], version: str) -> None:
    """Mirrors this version's R2 artifacts to a public GitHub Release, so
    the weights actually become downloadable by anyone -- goodgorithm-
    models itself stays private/authenticated-only. Idempotent: a version
    can get re-promoted (e.g. a rollback republishing an older version),
    and re-releasing identical artifacts under the same tag would just be
    noise, so an existing release for this version is left alone."""
    tag = _release_tag(prefix, version)
    if _release_exists(tag):
        print(f"GitHub release {tag} already exists, skipping")
        return

    key_prefix = f"{prefix}/{version}"
    model_config = json.loads(client.get_object(Bucket=_bucket(), Key=f"{key_prefix}/config.json")["Body"].read())

    notes = (
        f"`{prefix}` `{version}`, promoted to production.\n\n"
        f"- Dataset composition: {json.dumps(model_config.get('dataset_composition', {}))}\n"
        f"- Eval numbers: see `config.json` in this release's assets\n\n"
        "See `CLAUDE.md` and the matching `release-*` skill for how this was trained and published."
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        paths = []
        for artifact in artifacts:
            data = client.get_object(Bucket=_bucket(), Key=f"{key_prefix}/{artifact}")["Body"].read()
            path = tmpdir / artifact
            path.write_bytes(data)
            paths.append(str(path))

        subprocess.run(
            [
                "gh",
                "release",
                "create",
                tag,
                *paths,
                "--repo",
                GITHUB_REPO,
                "--title",
                f"{prefix} {version}",
                "--notes",
                notes,
            ],
            check=True,
        )
    print(f"created public GitHub release {tag}")


def publish(client, prefix: str, artifacts: list[str], version: str) -> None:
    """Points `<prefix>/latest.json` at `version`. Checks all required
    artifacts actually exist first -- publishing a version that's missing
    one would otherwise fail silently until the next time the inference
    side tries to load it, in production. Also makes the version publicly
    downloadable (see create_github_release) -- promoting a version to
    production and making it public happen together now, not as separate
    optional steps, so the two can't drift out of sync."""
    for artifact in artifacts:
        key = f"{prefix}/{version}/{artifact}"
        try:
            client.head_object(Bucket=_bucket(), Key=key)
        except client.exceptions.ClientError:
            sys.exit(
                f"{key} not found in R2 -- has version {version!r} actually "
                f"been uploaded? (run the training notebook first)"
            )

    create_github_release(client, prefix, artifacts, version)

    client.put_object(
        Bucket=_bucket(),
        Key=f"{prefix}/latest.json",
        Body=json.dumps({"version": version}).encode(),
        ContentType="application/json",
    )
    print(f"{prefix}/latest.json now points to {version!r}")
    print(
        "The matching service picks this up the next time a process starts "
        "(it resolves the version once per process, on first use)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, choices=sorted(MODEL_REGISTRY), help="which model type to act on")
    parser.add_argument("command", choices=["current", "list", "publish"])
    parser.add_argument("version", nargs="?", help="required for `publish`")
    args = parser.parse_args()

    registry_entry = MODEL_REGISTRY[args.model]
    prefix = registry_entry["prefix"]
    artifacts = registry_entry["artifacts"]

    client = _client()

    if args.command == "current":
        version = current(client, prefix)
        print(version if version else "(nothing published as latest yet)")
    elif args.command == "list":
        versions = list_versions(client, prefix)
        live = current(client, prefix)
        if not versions:
            print("(no versions found)")
        for v in versions:
            print(f"{v}{'  <- latest' if v == live else ''}")
    elif args.command == "publish":
        if not args.version:
            sys.exit("usage: uv run python r2_release.py --model <sentiment|category> publish <version>")
        publish(client, prefix, artifacts, args.version)


if __name__ == "__main__":
    main()
