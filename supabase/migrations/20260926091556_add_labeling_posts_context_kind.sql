-- Whether a candidate's quote_content is the post it quotes or the thread
-- root it replies to, so the review UI can label the context block
-- ("Quoting" / "Replying to"). Same values as processed_posts.context_kind
-- ('quote' / 'reply'); NULL when the post has no context, and for rows
-- inserted before this column existed (the kind isn't recoverable from what
-- labeling.posts stores).
ALTER TABLE labeling.posts ADD COLUMN context_kind TEXT;
