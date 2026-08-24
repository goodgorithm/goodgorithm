import Hls from "hls.js";
import { useEffect, useRef, useState } from "react";

import type { Attachment } from "../api/types";
import styles from "./VideoPlayer.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type VideoAttachment = Extract<Attachment, { kind: "video" }>;

// Mastodon's playlistUrl is already a plain MP4 - native <video src> plays
// it directly everywhere. Bluesky's is an HLS .m3u8 playlist, needing
// hls.js's Media Source Extensions parsing on most engines.
//
// Must check for "probably" specifically, not just non-empty - canPlayType
// returns "", "maybe", or "probably". Modern Chromium *and* Playwright's
// WebKit build both return "maybe" here despite not actually being able
// to play a real multi-rendition HLS manifest natively - treating "maybe"
// as supported skips hls.js entirely and silently fails (network state
// goes straight to NETWORK_NO_SOURCE, no error ever surfaces). "probably"
// is the only value actually worth trusting; in practice that routes every
// engine through hls.js today, which is fine - hls.js works on any
// MSE-capable browser. See e2e/video.spec.ts, which runs this exact check
// against real Chromium/Firefox/WebKit on every change.
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
    // Surfaces real hls.js failures instead of failing silently -- a fatal
    // error here would otherwise leave the video stuck with nothing
    // visible in the console.
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
