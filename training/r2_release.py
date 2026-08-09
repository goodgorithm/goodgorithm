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
import sys

import boto3

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


def publish(client, version: str) -> None:
    """Points sentiment-cnn/latest.json at `version`. Checks all three
    artifacts actually exist first -- publishing a version that's missing
    e.g. vocab.json would otherwise fail silently until the next time
    processing/ tries to load it, in production."""
    for artifact in REQUIRED_ARTIFACTS:
        key = f"{PREFIX}/{version}/{artifact}"
        try:
            client.head_object(Bucket=_bucket(), Key=key)
        except client.exceptions.ClientError:
            sys.exit(
                f"{key} not found in R2 -- has version {version!r} actually "
                f"been uploaded? (run the training notebook first)"
            )

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
