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

  it("falls back to the default for the old ?category=all (Full feed, removed - issue #33)", () => {
    window.history.pushState(null, "", "/?category=all");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBe("arts_culture");
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
