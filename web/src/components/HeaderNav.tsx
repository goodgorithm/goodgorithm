import { useEffect, useRef, useState } from "react";

import { GitHubIcon } from "./GitHubIcon";
import styles from "./HeaderNav.module.css";

// Header nav: an inline pill row on wide viewports, collapsed behind a burger
// button on narrow ones. The item set grows over time (FAQ, Updates, Privacy,
// ...), so on a narrow phone viewport the inline row can't fit. matchMedia
// (not element measurement) picks the mode, matching how CategorySelector
// solved its analogous layout problem with a media query rather than JS
// geometry.
const NARROW_QUERY = "(max-width: 30rem)";

function matchesNarrow(): boolean {
  return typeof window !== "undefined" && window.matchMedia(NARROW_QUERY).matches;
}

type Page = { path: string; label: string };

export function HeaderNav({
  pages,
  activePath,
  onNavigate,
}: {
  pages: Page[];
  activePath: string;
  onNavigate: (path: string) => void;
}) {
  const [isNarrow, setIsNarrow] = useState(matchesNarrow);
  const [menuOpen, setMenuOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);
  const burgerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const mql = window.matchMedia(NARROW_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      setIsNarrow(event.matches);
      if (!event.matches) setMenuOpen(false);
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        burgerRef.current?.focus();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (navRef.current && !navRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [menuOpen]);

  const go = (path: string) => {
    onNavigate(path);
    setMenuOpen(false);
  };

  const pageLinks = pages
    .filter((page) => page.path !== activePath)
    .map((page) => (
      <button
        key={page.path}
        type="button"
        className={styles.navLink}
        onClick={() => go(page.path)}
      >
        {page.label}
      </button>
    ));

  const githubLink = (
    <a
      className={styles.navLink}
      href="https://github.com/goodgorithm/goodgorithm"
      target="_blank"
      rel="noreferrer noopener"
      aria-label="GitHub"
    >
      <GitHubIcon />
    </a>
  );

  return (
    <nav className={styles.nav} ref={navRef}>
      {isNarrow ? (
        <>
          <button
            type="button"
            ref={burgerRef}
            className={styles.burger}
            aria-label="Menu"
            aria-expanded={menuOpen}
            aria-controls="header-menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
              <path
                d="M3 5h14M3 10h14M3 15h14"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          {menuOpen && (
            <ul id="header-menu" className={styles.menu}>
              {[...pageLinks, githubLink].map((node, i) => (
                <li key={i}>{node}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className={styles.inline}>
          {pageLinks}
          {githubLink}
        </div>
      )}
    </nav>
  );
}
