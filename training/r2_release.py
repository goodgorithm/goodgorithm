#!/usr/bin/env python3
"""Inspect, promote, or roll back the live sentiment CNN version in R2.

Flips sentiment-cnn/latest.json (what processing/'s sentiment.py actually
reads) without needing to re-run the training notebook. Useful for:

  - promoting a version the notebook already uploaded with
    PUBLISH_AS_LATEST=False (the notebook's default -- publishing artifacts
    and promoting to production are deliberately separate steps)
  - rolling back to a previously-published version if a new one turns out
    to be worse in production than eval numbers suggested
  - checking what's currently live, and what versions exist at all

`publish` also mirrors the version's three artifacts to a public GitHub
Release (sentiment-cnn-<version>) -- goodgorithm-models is a private R2
bucket (no r2.dev/custom domain configured, confirmed 2026-08-12), so
without this the "we open-source model weights" claim in MISSION.md/the
Algorithm page wasn't actually true: the weights existed, but nobody
outside the project could download them. Making the live version public
is now a required part of promoting it, not a separate/optional step.
Requires the `gh` CLI, authenticated, with access to goodgorithm/goodgorithm.

Usage:
    uv run python r2_release.py current
    uv run python r2_release.py list
    uv run python r2_release.py publish <version>

Requires the same R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY /
R2_BUCKET_NAME env vars processing/ uses -- see .env.example in the repo
root. Mirrors processing/src/model_store.py's registry layout exactly:
sentiment-cnn/<version>/{model.onnx,vocab.json,config.json}, plus a single
mutable sentiment-cnn/latest.json pointer.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3

GITHUB_REPO = "goodgorithm/goodgorithm"

PREFIX = "sentiment-cnn"
REQUIRED_ARTIFACTS = ["model.onnx", "vocab.json", "config.json"]

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


def current(client) -> str | None:
    try:
        body = client.get_object(Bucket=_bucket(), Key=f"{PREFIX}/latest.json")["Body"].read()
    except client.exceptions.NoSuchKey:
        return None
    return json.loads(body)["version"]


def list_versions(client) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    versions: set[str] = set()
    for page in paginator.paginate(Bucket=_bucket(), Prefix=f"{PREFIX}/", Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            name = entry["Prefix"][len(f"{PREFIX}/") :].rstrip("/")
            if name:
                versions.add(name)
    return sorted(versions)


def _release_tag(version: str) -> str:
    return f"sentiment-cnn-{version}"


def _release_exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", GITHUB_REPO],
        capture_output=True,
    )
    return result.returncode == 0


def create_github_release(client, version: str) -> None:
    """Mirrors this version's three R2 artifacts to a public GitHub Release,
    so the weights actually become downloadable by anyone -- goodgorithm-
    models itself stays private/authenticated-only. Idempotent: a version
    can get re-promoted (e.g. a rollback republishing an older version),
    and re-releasing identical artifacts under the same tag would just be
    noise, so an existing release for this version is left alone."""
    tag = _release_tag(version)
    if _release_exists(tag):
        print(f"GitHub release {tag} already exists, skipping")
        return

    prefix = f"{PREFIX}/{version}"
    model_config = json.loads(client.get_object(Bucket=_bucket(), Key=f"{prefix}/config.json")["Body"].read())

    notes = (
        f"Sentiment CNN `{version}`, promoted to production.\n\n"
        f"- Trained against `processing/src/sentiment_model.py` @ "
        f"`{model_config.get('architecture_source_commit', '?')}`\n"
        f"- Dataset composition: {json.dumps(model_config.get('dataset_composition', {}))}\n"
        f"- Held-out validation macro-F1: {model_config.get('best_val_macro_f1', '?')}\n\n"
        "See `CLAUDE.md`'s Sentiment model loading section and the "
        "`release-sentiment-model` skill for how this was trained and published."
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        paths = []
        for artifact in REQUIRED_ARTIFACTS:
            data = client.get_object(Bucket=_bucket(), Key=f"{prefix}/{artifact}")["Body"].read()
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
                f"Sentiment CNN {version}",
                "--notes",
                notes,
            ],
            check=True,
        )
    print(f"created public GitHub release {tag}")


def publish(client, version: str) -> None:
    """Points sentiment-cnn/latest.json at `version`. Checks all three
    artifacts actually exist first -- publishing a version that's missing
    e.g. vocab.json would otherwise fail silently until the next time
    processing/ tries to load it, in production. Also makes the version
    publicly downloadable (see create_github_release) -- promoting a
    version to production and making it public happen together now, not
    as separate optional steps, so the two can't drift out of sync."""
    for artifact in REQUIRED_ARTIFACTS:
        key = f"{PREFIX}/{version}/{artifact}"
        try:
            client.head_object(Bucket=_bucket(), Key=key)
        except client.exceptions.ClientError:
            sys.exit(
                f"{key} not found in R2 -- has version {version!r} actually "
                f"been uploaded? (run the training notebook first)"
            )

    create_github_release(client, version)

    client.put_object(
        Bucket=_bucket(),
        Key=f"{PREFIX}/latest.json",
        Body=json.dumps({"version": version}).encode(),
        ContentType="application/json",
    )
    print(f"sentiment-cnn/latest.json now points to {version!r}")
    print("processing/ picks this up the next time a process starts "
          "(it resolves the version once per process, on first sentiment score).")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"current", "list", "publish"}:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    client = _client()

    if command == "current":
        version = current(client)
        print(version if version else "(nothing published as latest yet)")
    elif command == "list":
        versions = list_versions(client)
        live = current(client)
        if not versions:
            print("(no versions found)")
        for v in versions:
            print(f"{v}{'  <- latest' if v == live else ''}")
    elif command == "publish":
        if len(sys.argv) < 3:
            sys.exit("usage: uv run python r2_release.py publish <version>")
        publish(client, sys.argv[2])


if __name__ == "__main__":
    main()
