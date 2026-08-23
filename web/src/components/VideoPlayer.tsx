import Hls from "hls.js";
import { useEffect, useRef, useState } from "react";

import type { Attachment } from "../api/types";
import styles from "./VideoPlayer.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type VideoAttachment = Extract<Attachment, { kind: "video" }>;

// Mastodon's playlistUrl is already a plain MP4 - native <video src> plays
// it directly everywhere. Bluesky's is an HLS .m3u8 playlist: Safari plays
// that natively too (canPlayType), but every other engine needs hls.js to
// parse the manifest via Media Source Extensions.
//
// Must check for "probably" specifically, not just non-empty (issue #66) -
// canPlayType returns "", "maybe", or "probably", and modern Chromium
// returns "maybe" here despite not actually being able to play a real
// multi-rendition HLS manifest natively. Treating "maybe" as supported skips
// hls.js entirely and silently fails (network state goes straight to
// NETWORK_NO_SOURCE, no error ever surfaces). Only Safari reliably returns
// "probably" for this MIME type - that's the actual native-support signal.
function isNativeHlsSupported(video: HTMLVideoElement): boolean {
  return video.canPlayType("application/vnd.apple.mpegurl") === "probably";
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
    // hls.js failures were previously completely silent -- issue #66's
    // actual root cause (isNativeHlsSupported wrongly treating Chromium's
    // "maybe" canPlayType answer as real support) meant this code path
    // wasn't even the problem, but a future real hls.js failure deserves
    // to be visible rather than a silent black box like this one was.
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) console.error("[hls.js]", data.type, data.details);
    });
    hls.loadSource(playlistUrl);
    hls.attachMedia(video);
    return () => hls.destroy();
  }, [playlistUrl]);

  return videoRef;
}

export function VideoPlayer({ video, sensitive }: { video: VideoAttachment; sensitive: boolean }) {
  const videoRef = useHlsSource(video.playlistUrl);
  // WCAG 2.2.2: a looping autoplay video needs a way to be paused - the
  // native <video controls> attribute deliberately isn't used for the
  // gif-style case (autoplay/loop/muted with a visible scrubber reads as a
  // real video player, not a gif), so this is a small dedicated toggle
  // instead. Synced to real play/pause events, not just the click that
  // caused them, in case autoplay itself gets blocked by browser policy.
  const [playing, setPlaying] = useState(true);

  return (
    <SensitiveMedia sensitive={sensitive} revealLabel="Show video">
      {video.isGif ? (
        <div className={styles.gifWrapper}>
          <video
            ref={videoRef}
            className={styles.video}
            poster={video.thumbnailUrl ?? undefined}
            style={video.width && video.height ? { aspectRatio: `${video.width} / ${video.height}` } : undefined}
            autoPlay
            loop
            muted
            playsInline
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
          <button
            type="button"
            className={styles.gifToggle}
            aria-label={playing ? "Pause" : "Play"}
            onClick={() => (playing ? videoRef.current?.pause() : videoRef.current?.play())}
          >
            {playing ? "⏸" : "▶"}
          </button>
        </div>
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
