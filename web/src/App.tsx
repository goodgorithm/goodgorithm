import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import algorithmSource from "./content/algorithm.md?raw";
import missionSource from "./content/mission.md?raw";
import styles from "./App.module.css";
import { ContentPage } from "./components/ContentPage";
import { Feed } from "./components/Feed";
import { UpdatePrompt } from "./components/UpdatePrompt";
import { Wordmark } from "./components/Wordmark";
import { useLocation } from "./lib/useLocation";

const queryClient = new QueryClient();

// Static content pages reachable from the header nav. Adding a new one
// (e.g. the content policy page, issue #4) means adding a content/*.md
// file and one entry here - App.tsx doesn't otherwise need to change.
const CONTENT_PAGES = [
  { path: "/mission", label: "Our mission", source: missionSource },
  { path: "/algorithm", label: "The algorithm", source: algorithmSource },
];

export default function App() {
  const [path, navigate] = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const activePage = CONTENT_PAGES.find((p) => p.path === path);

  useEffect(() => {
    document.title = activePage ? `${activePage.label} — Goodgorithm` : "Goodgorithm";
  }, [activePage]);

  // Don't leave the expanded menu open behind whatever page it navigated to.
  useEffect(() => {
    setNavOpen(false);
  }, [path]);

  return (
    <QueryClientProvider client={queryClient}>
      <main className={styles.main}>
        <UpdatePrompt />
        <header className={styles.header}>
          <button type="button" className={styles.logoButton} onClick={() => navigate("/")}>
            <Wordmark />
          </button>
          {/* Only shown below the narrow-viewport breakpoint (App.module.css)
              -- the nav row itself always renders above it, so this has
              nothing to toggle and stays hidden (issue #27: the header
              previously just overflowed off-screen with no indication more
              nav existed). */}
          <button
            type="button"
            className={styles.navToggle}
            aria-expanded={navOpen}
            aria-label={navOpen ? "Close menu" : "Open menu"}
            onClick={() => setNavOpen((open) => !open)}
          >
            {navOpen ? "✕" : "☰"}
          </button>
          <nav className={navOpen ? `${styles.nav} ${styles.navOpen}` : styles.nav}>
            {CONTENT_PAGES.filter((p) => p.path !== path).map((p) => (
              <button
                key={p.path}
                type="button"
                className={styles.navLink}
                onClick={() => navigate(p.path)}
              >
                {p.label}
              </button>
            ))}
            <a
              className={styles.navLink}
              href="https://github.com/goodgorithm/goodgorithm"
              target="_blank"
              rel="noreferrer noopener"
            >
              GitHub
            </a>
          </nav>
        </header>
        {activePage ? (
          <ContentPage source={activePage.source} onBack={() => navigate("/")} />
        ) : (
          <Feed navigate={navigate} />
        )}
      </main>
    </QueryClientProvider>
  );
}
