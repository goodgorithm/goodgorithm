import gzip
import json
from datetime import date, datetime, timezone

import main
import pipeline
from infra.db import ExportablePost
from pipeline_stages import corpus_export


def _post(raw_post_id, text, source="bluesky", day="2026-09-05", category="arts_culture"):
    ts = datetime.fromisoformat(f"{day}T12:00:00+00:00")
    return ExportablePost(
        raw_post_id=raw_post_id,
        source=source,
        text=text,
        created_at=ts,
        category=category,
        category_method="tfidf_lr_v1",
        pipeline_version="v8",
        dedup_cluster_id="11111111-1111-1111-1111-111111111111",
        processed_at=ts,
    )


class FakeCorpusStore:
    def __init__(self, objects=None, fail_keys=()):
        self.objects: dict[str, bytes] = dict(objects or {})
        self.fail_keys = set(fail_keys)
        self.put_keys: list[str] = []

    def put_bytes(self, key, data, content_type="application/gzip"):
        if any(f in key for f in self.fail_keys):
            raise RuntimeError("simulated R2 failure")
        self.put_keys.append(key)
        self.objects[key] = data

    def put_fileobj(self, key, fileobj, content_type="application/gzip"):
        self.put_keys.append(key)
        fileobj.seek(0)
        self.objects[key] = fileobj.read()

    def get_bytes(self, key):
        return self.objects[key]

    def list_keys(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))


# --- pure helpers -----------------------------------------------------------


def test_build_objects_groups_by_source_and_date_and_gzips_valid_ndjson():
    posts = [
        _post("a", "hello world", source="bluesky", day="2026-09-05"),
        _post("b", "second post", source="bluesky", day="2026-09-05"),
        _post("c", "masto post", source="mastodon", day="2026-09-05"),
        _post("d", "next day", source="bluesky", day="2026-09-06"),
    ]
    objects = corpus_export.build_objects("corpus", posts)

    assert len(objects) == 3  # (bluesky,5), (mastodon,5), (bluesky,6)
    by_ids = {tuple(sorted(o.raw_post_ids)): o for o in objects}
    assert ("a", "b") in by_ids
    assert ("c",) in by_ids
    assert ("d",) in by_ids

    obj = by_ids[("a", "b")]
    assert obj.key.startswith("corpus/raw/2026/09/05/bluesky-")
    assert obj.key.endswith(".ndjson.gz")
    records = [json.loads(line) for line in gzip.decompress(obj.data).decode().splitlines()]
    assert [r["text"] for r in records] == ["hello world", "second post"]
    assert records[0]["source"] == "bluesky"
    assert records[0]["category"] == "arts_culture"
    assert records[0]["pipeline_version"] == "v8"
    assert "sentiment_score" not in records[0]
    assert "raw_post_id" not in records[0]
    assert "author_id" not in records[0]


def test_iter_records_round_trips_build_objects_output():
    posts = [_post("a", "round trip me"), _post("b", "and me too")]
    [obj] = corpus_export.build_objects("corpus", posts)
    assert [r["text"] for r in corpus_export.iter_records(obj.data)] == ["round trip me", "and me too"]


def test_dedup_key_is_stripped_text():
    assert corpus_export.dedup_key({"text": "  spaced  "}) == "spaced"
    assert corpus_export.dedup_key({"text": "a b"}) == "a b"  # internal whitespace preserved
    assert corpus_export.dedup_key({}) == ""


# --- export_corpus sweep --------------------------------------------------


def test_export_corpus_noop_when_nothing_pending(monkeypatch):
    monkeypatch.setattr(pipeline.db, "fetch_unexported_posts", lambda batch, age: [])
    monkeypatch.setattr(pipeline.db, "mark_exported", lambda ids: (_ for _ in ()).throw(AssertionError()))
    assert pipeline.export_corpus() == 0


def test_export_corpus_marks_only_successfully_put_ids(monkeypatch):
    posts = [
        _post("a", "one", source="bluesky", day="2026-09-05"),
        _post("b", "two", source="mastodon", day="2026-09-05"),  # this group's PUT fails
    ]
    monkeypatch.setattr(pipeline.db, "fetch_unexported_posts", lambda batch, age: posts)
    fake = FakeCorpusStore(fail_keys=["mastodon-"])
    monkeypatch.setattr(pipeline.corpus_store, "CorpusStore", lambda: fake)
    marked = []
    monkeypatch.setattr(pipeline.db, "mark_exported", lambda ids: marked.extend(ids))

    exported = pipeline.export_corpus()

    assert exported == 1
    assert marked == ["a"]  # "b"'s group failed -> left unmarked for retry
    assert any(k.startswith("corpus/raw/2026/09/05/bluesky-") for k in fake.put_keys)
    assert not any("mastodon" in k for k in fake.put_keys)


# --- compact_corpus sweep -----------------------------------------------


def _raw_obj(records):
    body = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records)
    return gzip.compress(body.encode())


def test_compact_corpus_dedups_exact_text_and_skips_current_and_sharded_months(monkeypatch):
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    objects = {
        # a complete month with an exact-duplicate across two raw objects
        "corpus/raw/2026/07/01/bluesky-1-x.ndjson.gz": _raw_obj(
            [{"text": "dup me", "source": "bluesky"}, {"text": "unique a", "source": "bluesky"}]
        ),
        "corpus/raw/2026/07/02/mastodon-2-y.ndjson.gz": _raw_obj(
            [{"text": "dup me", "source": "mastodon"}, {"text": "unique b", "source": "mastodon"}]
        ),
        # a month that already has a shard -> skipped
        "corpus/raw/2026/06/15/bluesky-3-z.ndjson.gz": _raw_obj([{"text": "old", "source": "bluesky"}]),
        "corpus/shards/2026-06.ndjson.gz": _raw_obj([{"text": "old", "source": "bluesky"}]),
        # current month -> still open, skipped
        f"corpus/raw/{current_month.replace('-', '/')}/10/bluesky-4-w.ndjson.gz": _raw_obj(
            [{"text": "fresh", "source": "bluesky"}]
        ),
    }
    fake = FakeCorpusStore(objects)
    monkeypatch.setattr(pipeline.corpus_store, "CorpusStore", lambda: fake)

    compacted = pipeline.compact_corpus()

    assert compacted == 1  # only 2026-07
    shard = fake.objects["corpus/shards/2026-07.ndjson.gz"]
    texts = [json.loads(line)["text"] for line in gzip.decompress(shard).decode().splitlines()]
    assert texts == ["dup me", "unique a", "unique b"]  # one "dup me", first-wins
    assert "corpus/shards/2026-06.ndjson.gz" in fake.objects  # untouched
    assert not any(current_month in k for k in fake.put_keys)


# --- daily compaction scheduling ---------------------------------------


def test_daily_task_due_fires_once_per_day_at_or_after_the_hour():
    hour = 4
    # before the hour, never run today
    assert not main._daily_task_due(datetime(2026, 9, 8, 3, 59, tzinfo=timezone.utc), hour, None)
    # at/after the hour, not yet run today -> due
    assert main._daily_task_due(datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc), hour, None)
    assert main._daily_task_due(datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc), hour, date(2026, 9, 7))
    # already ran today -> not due again
    assert not main._daily_task_due(datetime(2026, 9, 8, 20, 0, tzinfo=timezone.utc), hour, date(2026, 9, 8))
    # next day -> due again
    assert main._daily_task_due(datetime(2026, 9, 9, 4, 1, tzinfo=timezone.utc), hour, date(2026, 9, 8))


def test_daily_task_due_restart_after_the_hour_runs_immediately():
    # last_run_date resets to None on restart; a 30d elapsed timer could not do this
    assert main._daily_task_due(datetime(2026, 9, 8, 22, 0, tzinfo=timezone.utc), 4, None)


def test_compact_corpus_noop_when_all_months_sharded_or_current(monkeypatch):
    fake = FakeCorpusStore(
        {
            "corpus/raw/2026/07/01/bluesky-1-x.ndjson.gz": _raw_obj([{"text": "a"}]),
            "corpus/shards/2026-07.ndjson.gz": _raw_obj([{"text": "a"}]),
        }
    )
    monkeypatch.setattr(pipeline.corpus_store, "CorpusStore", lambda: fake)
    assert pipeline.compact_corpus() == 0
