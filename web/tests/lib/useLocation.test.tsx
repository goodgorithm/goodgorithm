import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useLocation } from "../../src/lib/useLocation";

describe("useLocation", () => {
  afterEach(() => {
    window.history.pushState(null, "", "/");
  });

  it("starts from the current pathname", () => {
    window.history.pushState(null, "", "/mission");

    const { result } = renderHook(() => useLocation());

    expect(result.current[0]).toBe("/mission");
  });

  it("navigate updates both the path and browser history", () => {
    const { result } = renderHook(() => useLocation());

    act(() => result.current[1]("/mission"));

    expect(result.current[0]).toBe("/mission");
    expect(window.location.pathname).toBe("/mission");
  });

  it("responds to browser back/forward (popstate)", () => {
    const { result } = renderHook(() => useLocation());

    act(() => result.current[1]("/mission"));
    act(() => {
      window.history.pushState(null, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current[0]).toBe("/");
  });
});
