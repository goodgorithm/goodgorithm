import os

# Bluesky's own public, unauthenticated AppView instance -- not something
# an operator would tune, so it's not an env var, same as ingestion/'s
# Jetstream URL. Shared by every pipeline stage that calls the AppView
# (quote_resolver.py, moderation_recheck.py, author_resolver.py), same
# "shared helper, not hand-duplicated" pattern as util/url_extract.py. See
# the wiki's Bluesky Protocol page.
APPVIEW_BASE = "https://public.api.bsky.app/xrpc"

# app.bsky.feed.getPosts' documented max URIs per call -- an external API
# limit, not a tunable; raising this would just make oversized batches
# fail against Bluesky's own enforcement.
GET_POSTS_MAX_URIS = 25

# Per-batch HTTP timeout for any getPosts call against the AppView above.
# One shared knob, not one per consumer -- it's the same endpoint and the
# same network characteristics regardless of which pipeline stage is
# calling it. See the wiki's Configuration page.
APPVIEW_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("APPVIEW_REQUEST_TIMEOUT_SECONDS", "10"))
