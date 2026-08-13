import type { CapacitorConfig } from "@capacitor/cli";

// Deliberately no `server.cleartext`/`android.allowMixedContent` and no
// `plugins.CapacitorHttp` block -- CapacitorHttp (native fetch/XHR
// proxying, opt-in since Capacitor 6) stays off by not configuring it.
// Nothing here needs its CORS-bypass (api/'s CORS is already `origin: true`,
// api/src/app.ts), and enabling it is the documented cause of hls.js's
// .m3u8/.ts segment requests breaking on Android (issue #9) -- leaving it
// off keeps hls.js on ordinary web-platform fetch, same as it already
// behaves in a normal Android WebView/Chrome context.
const config: CapacitorConfig = {
  appId: "com.goodgorithm.app",
  appName: "Goodgorithm",
  webDir: "dist",
};

export default config;
