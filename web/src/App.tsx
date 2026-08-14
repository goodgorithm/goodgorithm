import { Capacitor } from "@capacitor/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";

import faqSource from "./content/faq.md?raw";
import styles from "./App.module.css";
import { ContentPage } from "./components/ContentPage";
import { Feed } from "./components/Feed";
import { GitHubIcon } from "./components/GitHubIcon";
import { ScrollToTopButton } from "./components/ScrollToTopButton";
import { UpdatePrompt } from "./components/UpdatePrompt";
import { Wordmark } from "./components/Wordmark";
import { useLocation } from "./lib/useLocation";
import { useNativeStatusBar } from "./lib/useNativeStatusBar";

const queryClient = new QueryClient();

// Static content pages reachable from the header nav. Adding a new one
// means adding a content/*.md file and one entry here - App.tsx doesn't
// otherwise need to change. Mission/Algorithm/Content Policy moved to the
// GitHub Wiki (issue #31) - FAQ is the one page that stays in-app.
const CONTENT_PAGES = [{ path: "/faq", label: "FAQ", source: faqSource }];

export default function App() {
  const [path, navigate] = useLocation();
  const activePage = CONTENT_PAGES.find((p) => p.path === path);

  useNativeStatusBar();

  useEffect(() => {
    document.title = activePage ? `${activePage.label} — Goodgorithm` : "Goodgorithm";
  }, [activePage]);

  return (
    <QueryClientProvider client={queryClient}>
      <main className={styles.main}>
        {/* Capacitor's native WebView doesn't use a service worker the way a
            browser does, and UpdatePrompt's whole reason to exist -- a
            live service-worker swap needing a reload -- doesn't apply on
            native (app updates go through store review instead). Not
            rendering it is what keeps useRegisterSW (inside UpdatePrompt)
            from ever registering a service worker on native in the first
            place -- issue #9. */}
        {!Capacitor.isNativePlatform() && <UpdatePrompt />}
        <header className={styles.header}>
          <button type="button" className={styles.logoButton} onClick={() => navigate("/")}>
            <Wordmark />
          </button>
          <nav className={styles.nav}>
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
              aria-label="GitHub"
            >
              <GitHubIcon />
            </a>
          </nav>
        </header>
        {activePage ? (
          <ContentPage source={activePage.source} onBack={() => navigate("/")} />
        ) : (
          <Feed />
        )}
        <ScrollToTopButton />
      </main>
    </QueryClientProvider>
  );
}
