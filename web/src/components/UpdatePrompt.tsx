import { useState } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";

import styles from "./UpdatePrompt.module.css";

// vite.config.ts's registerType: "autoUpdate" means a new service worker
// self-activates and claims already-open tabs on its own (skipWaiting +
// clientsClaim) - useRegisterSW's onNeedRefresh callback never fires in
// this mode (only onNeedReload does, and only once the new SW has already
// taken over). Left alone, that path defaults to an immediate, unprompted
// window.location.reload() - jarring mid-read, and exactly the gap
// CLAUDE.md's Versioning & migration section documents: a stale tab could
// otherwise keep running old JS indefinitely against a freshly-deployed
// api/. This intercepts that default with a dismissable prompt instead of
// a forced reload. updateServiceWorker() is a no-op in "autoUpdate" mode
// (the new worker already took control before this callback fires) - a
// plain reload is what actually picks up the new JS bundle.
export function UpdatePrompt() {
  const [needsReload, setNeedsReload] = useState(false);

  useRegisterSW({
    onNeedReload() {
      setNeedsReload(true);
    },
  });

  if (!needsReload) return null;

  return (
    <div className={styles.banner} role="status">
      <span>A new version is available.</span>
      <button type="button" className={styles.reload} onClick={() => window.location.reload()}>
        Reload
      </button>
    </div>
  );
}
