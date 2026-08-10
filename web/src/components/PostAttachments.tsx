import type { Attachment, FeedPost } from "../api/types";
import { ImageGrid } from "./ImageGrid";
import { LinkCard } from "./LinkCard";
import { QuoteLink } from "./QuoteLink";
import { VideoPlayer } from "./VideoPlayer";

function isKind<K extends Attachment["kind"]>(kind: K) {
  return (a: Attachment): a is Extract<Attachment, { kind: K }> => a.kind === kind;
}

export function PostAttachments({ post }: { post: FeedPost }) {
  if (post.attachments.length === 0) return null;

  const images = post.attachments.filter(isKind("image"));
  const links = post.attachments.filter(isKind("link"));
  const videos = post.attachments.filter(isKind("video"));
  const quotes = post.attachments.filter(isKind("quote"));

  return (
    <div>
      {images.length > 0 && <ImageGrid images={images} sensitive={post.sensitive} />}
      {links.map((link) => (
        <LinkCard key={link.url} link={link} sensitive={post.sensitive} />
      ))}
      {videos.map((video) => (
        <VideoPlayer key={video.playlistUrl} video={video} sensitive={post.sensitive} />
      ))}
      {quotes.map((quote) => (
        <QuoteLink key={quote.url} quote={quote} />
      ))}
    </div>
  );
}
