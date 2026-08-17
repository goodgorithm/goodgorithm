import { Capacitor } from "@capacitor/core";
import { Style, StatusBar } from "@capacitor/status-bar";
import { useEffect } from "react";

// Keeps the native status bar's text/icon color in sync with the app's
// theme (theme.css's light/dark tokens, driven purely by
// prefers-color-scheme -- no manual toggle exists anywhere in this app).
// Web-only concerns: overlaysWebView defaults to true (the modern
// edge-to-edge pattern on both platforms, and the only mode
// setBackgroundColor even claims to support), so App.module.css's
// safe-area-inset padding, not a status bar background color, is what
// keeps content from drawing under it. No-op entirely on web. See the
// wiki's Web Internals page for the full native-app picture.
export function useNativeStatusBar(): void {
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    // Confusingly named by the plugin itself: Style.Dark means "light
    // text/icons, for a dark background", Style.Light means the reverse.
    // Caught, not just fire-and-forget: cosmetic-only, and this plugin
    // call reliably rejects in any environment that reports
    // isNativePlatform() true without a real native bridge underneath
    // (e.g. this behavior is exercised directly in App.test.tsx).
    const applyStyle = (isDark: boolean) => {
      StatusBar.setStyle({ style: isDark ? Style.Dark : Style.Light }).catch(() => {});
    };

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    applyStyle(media.matches);

    const onChange = (event: MediaQueryListEvent) => applyStyle(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
}
