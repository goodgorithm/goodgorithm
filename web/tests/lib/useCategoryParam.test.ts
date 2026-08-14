import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useCategoryParam } from "../../src/lib/useCategoryParam";

describe("useCategoryParam", () => {
  afterEach(() => {
    window.history.pushState(null, "", "/");
  });

  it("defaults to Arts & Culture with no ?category= param (issue #24)", () => {
    const { result } = renderHook(() => useCategoryParam());
    expect(result.current[0]).toBe("arts_culture");
  });

  it("rewrites a bare / URL to the default on mount (issue #24)", () => {
    renderHook(() => useCategoryParam());
    expect(window.location.search).toContain("category=arts_culture");
  });

  it("reads a valid ?category= param on mount", () => {
    window.history.pushState(null, "", "/?category=gaming");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBe("gaming");
  });

  it("reads ?category=all as null (Full feed)", () => {
    window.history.pushState(null, "", "/?category=all");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBeNull();
  });

  it("falls back to the default for an unrecognized category value", () => {
    window.history.pushState(null, "", "/?category=not-a-real-category");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBe("arts_culture");
  });

  it("selecting a category writes it to the URL", () => {
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1]("science_technology"));

    expect(result.current[0]).toBe("science_technology");
    expect(window.location.search).toContain("category=science_technology");
  });

  it("selecting null (Full feed) writes the explicit all value, surviving a reload (issue #24)", () => {
    window.history.pushState(null, "", "/?category=gaming");
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

    act(() => result.current[1]("science_technology"));
    act(() => {
      window.history.pushState(null, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current[0]).toBe("arts_culture");
  });
});
