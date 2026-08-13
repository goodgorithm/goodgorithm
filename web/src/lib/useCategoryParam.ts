import { useEffect, useState } from "react";

import { CATEGORIES, type Category } from "../api/types";

// Full feed's explicit URL value (issue #24) - deliberately not "absence of
// the param", since once absence means "default to Kindness & Community"
// (below), a Full-feed choice represented only by an absent param would
// silently revert to the default on every reload. Giving it its own value
// makes it survive a refresh exactly like the 8 real categories do.
const FULL_FEED_PARAM = "all";

// The landing default (issue #24, reversing #20's "no param = Full feed").
// Also what an absent OR unrecognized/stale ?category= value falls back to
// - CLAUDE.md's defensive-unknown-category handling, just pointed at the
// new default instead of Full feed.
const DEFAULT_CATEGORY: Category = "kindness_community";

function readCategory(): Category | null {
  const value = new URLSearchParams(window.location.search).get("category");
  if (value === FULL_FEED_PARAM) return null;
  if ((CATEGORIES as readonly string[]).includes(value ?? "")) return value as Category;
  return DEFAULT_CATEGORY;
}

// Mirrors useLocation.ts's hand-rolled pushState/popstate shape (no router
// lib in web/ by design) - kept separate from useLocation itself since the
// category param only ever applies to the feed route, not the content pages.
export function useCategoryParam(): [Category | null, (category: Category | null) => void] {
  const [category, setCategory] = useState<Category | null>(readCategory);

  useEffect(() => {
    const onPopState = () => setCategory(readCategory());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Makes the default explicit in the address bar rather than leaving it
  // implicit - an absent or garbage ?category= value silently resolving to
  // Kindness & Community underneath would leave the URL not reflecting
  // what's actually showing. Runs once on mount only: replaceState mutates
  // the current history entry, so there's no bare-/-or-garbage entry left
  // for back/forward to return to afterward - no popstate handling needed.
  useEffect(() => {
    const currentParam = new URLSearchParams(window.location.search).get("category");
    if (readCategory() === DEFAULT_CATEGORY && currentParam !== DEFAULT_CATEGORY) {
      const url = new URL(window.location.href);
      url.searchParams.set("category", DEFAULT_CATEGORY);
      window.history.replaceState(null, "", url);
    }
  }, []);

  const select = (next: Category | null) => {
    const url = new URL(window.location.href);
    url.searchParams.set("category", next ?? FULL_FEED_PARAM);
    window.history.pushState(null, "", url);
    setCategory(next);
  };

  return [category, select];
}
