import re

# Pure stdlib, zero project imports — same discipline as sentiment_model.py,
# and for the same reason: this file is imported both by the category
# classifier's training notebook (via a commit-pinned raw GitHub URL) and by
# processing/'s inference path, so text normalization can never drift
# between train and inference even though the two run in different
# environments.

_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"@[\w.-]+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = text.lower()
    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()
