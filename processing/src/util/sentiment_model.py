import re

# Pure stdlib, zero project imports, zero torch import — this file is
# imported both by the training notebook (via a commit-pinned raw GitHub
# URL) and by processing/'s inference path, so tokenization can never drift
# between train and inference even though the two run in different
# environments. Keeping it torch-free is what lets inference depend on
# onnxruntime instead of full PyTorch.

PAD_TOKEN = "<pad>"
UNK_TOKEN = "<unk>"
URL_TOKEN = "<url>"
USER_TOKEN = "<user>"
NUM_TOKEN = "<num>"

EMBEDDING_DIM = 100
FILTER_SIZES = (3, 4, 5)
NUM_FILTERS = 100
DROPOUT = 0.5
MAX_SEQ_LEN = 50
MAX_VOCAB_SIZE = 20000

_CAMEL_BOUNDARY_RE = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-zA-Z])(?=[0-9])|(?<=[0-9])(?=[a-zA-Z])"
)
_HASHTAG_RE = re.compile(r"#(\w+)")


def _split_camel_hashtags(text: str) -> str:
    """Same boundary-splitting logic as util/text_normalize.py's
    split_camel_hashtags -- duplicated rather than imported, since this
    file is fetched standalone via one pinned commit URL by the training
    notebook and is deliberately zero-project-imports (see module
    docstring); importing text_normalize.py here would mean the notebook
    fetching two pinned files instead of one. Keep both in sync by hand
    if the boundary logic ever changes.

    Must run before _TOKEN_RE ever sees the text, on the original-case
    string -- case boundaries are the whole signal, and once split, a
    hashtag's words fall through to the ordinary `word`/`num` token paths
    below like any other text, so _TOKEN_RE needs no hashtag-matching
    branch of its own."""
    return _HASHTAG_RE.sub(lambda m: ". " + _CAMEL_BOUNDARY_RE.sub(" ", m.group(1)), text)


_TOKEN_RE = re.compile(
    r"""
    (?P<url>https?://\S+|www\.\S+)
    |(?P<mention>@\w+)
    |(?P<emoticon>[:;=][\-o]?[)DdPp(\\/]|<3)
    |(?P<num>\d+)
    |(?P<word>[a-z']+)
    |(?P<punct>[!?.]+)
    """,
    re.VERBOSE,
)


def tokenize(text: str) -> list[str]:
    """Social-text-aware tokenizer: URLs/mentions collapse to placeholder
    tokens (their literal values are noise, not signal — mentions especially
    would otherwise bloat the vocab with one-off usernames), hashtags are
    split into their word content before matching (often carries real
    sentiment, e.g. "#blessed", and a multi-word CamelCase hashtag like
    "#GreatNewsToday" would otherwise glue into one almost-certainly-
    out-of-vocab token -- see _split_camel_hashtags), emoticons are
    preserved as their
    own tokens rather than stripped as punctuation. All-digit runs collapse
    to NUM_TOKEN — the specific value is noise the same way a URL is, but
    *that a number appeared* is kept (unlike anything else the regex
    doesn't match, which is silently dropped) since numbers plausibly carry
    sentiment-relevant signal ("married for 30 years", "won 10-0") even
    though the exact value likely doesn't."""
    text = _split_camel_hashtags(text)
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        kind = match.lastgroup
        if kind == "url":
            tokens.append(URL_TOKEN)
        elif kind == "mention":
            tokens.append(USER_TOKEN)
        elif kind == "num":
            tokens.append(NUM_TOKEN)
        else:
            tokens.append(match.group(kind))
    return tokens


def encode(tokens: list[str], vocab: dict[str, int]) -> list[int]:
    """Vocab lookup with UNK fallback, truncated/padded to MAX_SEQ_LEN.
    `vocab` must map PAD_TOKEN and UNK_TOKEN to real ids (PAD conventionally
    0, matching the embedding matrix's zeroed pad row)."""
    unk_id = vocab.get(UNK_TOKEN, 0)
    pad_id = vocab.get(PAD_TOKEN, 0)
    ids = [vocab.get(t, unk_id) for t in tokens[:MAX_SEQ_LEN]]
    if len(ids) < MAX_SEQ_LEN:
        ids.extend([pad_id] * (MAX_SEQ_LEN - len(ids)))
    return ids
