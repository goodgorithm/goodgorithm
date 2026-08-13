import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useCategoryParam } from "../../src/lib/useCategoryParam";

describe("useCategoryParam", () => {
  afterEach(() => {
    window.history.pushState(null, "", "/");
  });

  it("defaults to Kindness & Community with no ?category= param (issue #24)", () => {
    const { result } = renderHook(() => useCategoryParam());
    expect(result.current[0]).toBe("kindness_community");
  });

  it("rewrites a bare / URL to the default on mount (issue #24)", () => {
    renderHook(() => useCategoryParam());
    expect(window.location.search).toContain("category=kindness_community");
  });

  it("reads a valid ?category= param on mount", () => {
    window.history.pushState(null, "", "/?category=animals");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBe("animals");
  });

  it("reads ?category=all as null (Full feed)", () => {
    window.history.pushState(null, "", "/?category=all");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBeNull();
  });

  it("falls back to the default for an unrecognized category value", () => {
    window.history.pushState(null, "", "/?category=not-a-real-category");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBe("kindness_community");
  });

  it("selecting a category writes it to the URL", () => {
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1]("technology"));

    expect(result.current[0]).toBe("technology");
    expect(window.location.search).toContain("category=technology");
  });

  it("selecting null (Full feed) writes the explicit all value, surviving a reload (issue #24)", () => {
    window.history.pushState(null, "", "/?category=animals");
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1](null));

    expect(result.current[0]).toBeNull();
    expect(window.location.search).toContain("category=all");

    // simulates a reload: a fresh hook instance reading the same URL should
    // still resolve to Full feed, not silently revert to the default.
    const { result: afterReload } = renderHook(() => useCategoryParam());
    expect(afterReload.current[0]).toBeNull();
  });

  it("responds to browser back/forward (popstate)", () => {
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1]("technology"));
    act(() => {
      window.history.pushState(null, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current[0]).toBe("kindness_community");
  });
});
