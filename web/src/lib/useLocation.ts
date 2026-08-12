import { useEffect, useState } from "react";

// No routing library - one extra static page doesn't justify pulling one
// in (web/ has none today by design, per CLAUDE.md). This covers exactly
// what's needed: track the current pathname, push it on navigate, and stay
// in sync with browser back/forward.
export function useLocation(): [string, (path: string) => void] {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (to: string) => {
    if (to !== window.location.pathname) {
      window.history.pushState(null, "", to);
    }
    setPath(to);
  };

  return [path, navigate];
}
