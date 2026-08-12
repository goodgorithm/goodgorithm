import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useCategoryParam } from "../../src/lib/useCategoryParam";

describe("useCategoryParam", () => {
  afterEach(() => {
    window.history.pushState(null, "", "/");
  });

  it("defaults to null (Full feed) with no ?category= param", () => {
    const { result } = renderHook(() => useCategoryParam());
    expect(result.current[0]).toBeNull();
  });

  it("reads a valid ?category= param on mount", () => {
    window.history.pushState(null, "", "/?category=animals");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBe("animals");
  });

  it("falls back to null for an unrecognized category value", () => {
    window.history.pushState(null, "", "/?category=not-a-real-category");

    const { result } = renderHook(() => useCategoryParam());

    expect(result.current[0]).toBeNull();
  });

  it("selecting a category writes it to the URL", () => {
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1]("technology"));

    expect(result.current[0]).toBe("technology");
    expect(window.location.search).toContain("category=technology");
  });

  it("selecting null (Full feed) removes the param from the URL", () => {
    window.history.pushState(null, "", "/?category=animals");
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1](null));

    expect(result.current[0]).toBeNull();
    expect(window.location.search).not.toContain("category=");
  });

  it("responds to browser back/forward (popstate)", () => {
    const { result } = renderHook(() => useCategoryParam());

    act(() => result.current[1]("technology"));
    act(() => {
      window.history.pushState(null, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current[0]).toBeNull();
  });
});
