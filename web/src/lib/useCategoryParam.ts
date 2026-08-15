import { useEffect, useState } from "react";

import { CATEGORIES, type Category } from "../api/types";

// The landing default (issue #24). Also what an absent OR unrecognized/stale
// ?category= value falls back to - CLAUDE.md's defensive-unknown-category
// handling. This includes the old "all"/Full feed URL value (issue #33 -
// removed once there was enough content in every category that the risk of
// an unfiltered, unmoderated-by-category feed no longer earned its keep) -
// it's just another unrecognized string now, no special-case needed.
// "kindness_community" was the original default but doesn't exist in the
// trained-classifier taxonomy (issue #34) - arts_culture is the closest
// replacement in spirit (broadly appealing, not niche) and happens to be
// the highest-volume category too.
const DEFAULT_CATEGORY: Category = "arts_culture";

function readCategory(): Category {
  const value = new URLSearchParams(window.location.search).get("category");
  if ((CATEGORIES as readonly string[]).includes(value ?? "")) return value as Category;
  return DEFAULT_CATEGORY;
}

// Mirrors useLocation.ts's hand-rolled pushState/popstate shape (no router
// lib in web/ by design) - kept separate from useLocation itself since the
// category param only ever applies to the feed route, not the content pages.
export function useCategoryParam(): [Category, (category: Category) => void] {
  const [category, setCategory] = useState<Category>(readCategory);

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

  const select = (next: Category) => {
    const url = new URL(window.location.href);
    url.searchParams.set("category", next);
    window.history.pushState(null, "", url);
    setCategory(next);
  };

  return [category, select];
}
