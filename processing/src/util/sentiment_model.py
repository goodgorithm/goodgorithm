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

_TOKEN_RE = re.compile(
    r"""
    (?P<url>https?://\S+|www\.\S+)
    |(?P<mention>@\w+)
    |(?P<hashtag>\#\w+)
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
    would otherwise bloat the vocab with one-off usernames), hashtags keep
    their word content (often carries real sentiment, e.g. "#blessed"),
    emoticons are preserved as their own tokens rather than stripped as
    punctuation. All-digit runs collapse to NUM_TOKEN — the specific value
    is noise the same way a URL is, but *that a number appeared* is kept
    (unlike anything else the regex doesn't match, which is silently
    dropped) since numbers plausibly carry sentiment-relevant signal
    ("married for 30 years", "won 10-0") even though the exact value
    likely doesn't."""
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        kind = match.lastgroup
        if kind == "url":
            tokens.append(URL_TOKEN)
        elif kind == "mention":
            tokens.append(USER_TOKEN)
        elif kind == "hashtag":
            tokens.append(match.group("hashtag")[1:])
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
