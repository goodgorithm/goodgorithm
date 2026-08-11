import { lazy, Suspense } from "react";

import type { Attachment, FeedPost } from "../api/types";
import { ImageGrid } from "./ImageGrid";
import { LinkCard } from "./LinkCard";
import { QuoteLink } from "./QuoteLink";

// hls.js is a substantial media-parsing library and was shipping in every
// visitor's initial bundle even though most posts carry no video (and even
// on Safari, which doesn't need it - see VideoPlayer's native-HLS check).
// Split into its own chunk, fetched only when a post actually has a video.
const VideoPlayer = lazy(() => import("./VideoPlayer").then((m) => ({ default: m.VideoPlayer })));

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
      {videos.length > 0 && (
        <Suspense fallback={null}>
          {videos.map((video) => (
            <VideoPlayer key={video.playlistUrl} video={video} sensitive={post.sensitive} />
          ))}
        </Suspense>
      )}
      {quotes.map((quote) => (
        <QuoteLink key={quote.url} quote={quote} />
      ))}
    </div>
  );
}
