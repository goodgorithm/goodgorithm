import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Explicit cleanup - RTL's auto-cleanup only self-registers when it detects
// a global afterEach, but tests here import afterEach explicitly rather than
// relying on vitest's globals mode.
afterEach(cleanup);
