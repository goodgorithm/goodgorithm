import Hls from "hls.js";
import { useEffect, useRef } from "react";

import type { Attachment } from "../api/types";
import styles from "./VideoPlayer.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type VideoAttachment = Extract<Attachment, { kind: "video" }>;

// Mastodon's playlistUrl is already a plain MP4 - native <video src> plays
// it directly everywhere. Bluesky's is an HLS .m3u8 playlist: Safari plays
// that natively too (canPlayType), but every other engine needs hls.js to
// parse the manifest via Media Source Extensions.
function isNativeHlsSupported(video: HTMLVideoElement): boolean {
  return video.canPlayType("application/vnd.apple.mpegurl") !== "";
}

function useHlsSource(playlistUrl: string) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!playlistUrl.endsWith(".m3u8") || isNativeHlsSupported(video)) {
      video.src = playlistUrl;
      return;
    }

    if (!Hls.isSupported()) return; // no HLS path available - browser just won't play this one

    const hls = new Hls();
    hls.loadSource(playlistUrl);
    hls.attachMedia(video);
    return () => hls.destroy();
  }, [playlistUrl]);

  return videoRef;
}

export function VideoPlayer({ video, sensitive }: { video: VideoAttachment; sensitive: boolean }) {
  const videoRef = useHlsSource(video.playlistUrl);

  return (
    <SensitiveMedia sensitive={sensitive} revealLabel="Show video">
      {video.isGif ? (
        <video
          ref={videoRef}
          className={styles.video}
          poster={video.thumbnailUrl ?? undefined}
          style={video.width && video.height ? { aspectRatio: `${video.width} / ${video.height}` } : undefined}
          autoPlay
          loop
          muted
          playsInline
        />
      ) : (
        <video
          ref={videoRef}
          className={styles.video}
          poster={video.thumbnailUrl ?? undefined}
          style={video.width && video.height ? { aspectRatio: `${video.width} / ${video.height}` } : undefined}
          controls
          playsInline
        />
      )}
    </SensitiveMedia>
  );
}
