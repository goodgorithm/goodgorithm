import { useEffect, useState } from "react";

import { CATEGORIES, type Category } from "../api/types";

function readCategory(): Category | null {
  const value = new URLSearchParams(window.location.search).get("category");
  return (CATEGORIES as readonly string[]).includes(value ?? "") ? (value as Category) : null;
}

// Mirrors useLocation.ts's hand-rolled pushState/popstate shape (no router
// lib in web/ by design) - kept separate from useLocation itself since the
// category param only ever applies to the feed route, not the content pages.
// Unrecognized/stale ?category= values fall back to null (Full feed), same
// defensive-unknown-category handling CLAUDE.md already specifies elsewhere.
export function useCategoryParam(): [Category | null, (category: Category | null) => void] {
  const [category, setCategory] = useState<Category | null>(readCategory);

  useEffect(() => {
    const onPopState = () => setCategory(readCategory());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const select = (next: Category | null) => {
    const url = new URL(window.location.href);
    if (next) {
      url.searchParams.set("category", next);
    } else {
      url.searchParams.delete("category");
    }
    window.history.pushState(null, "", url);
    setCategory(next);
  };

  return [category, select];
}
