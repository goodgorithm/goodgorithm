-- Lets deleting an old raw_posts row automatically clean up its
-- processed_posts row too, instead of failing on the FK or requiring
-- callers to delete from both tables in the right order.
ALTER TABLE processed_posts DROP CONSTRAINT processed_posts_raw_post_id_fkey;
ALTER TABLE processed_posts ADD CONSTRAINT processed_posts_raw_post_id_fkey
  FOREIGN KEY (raw_post_id) REFERENCES raw_posts(id) ON DELETE CASCADE;
