/**
 * Vitest global setup — registers @testing-library/jest-dom matchers on the
 * global expect so individual test files can assert
 * .toBeInTheDocument() / .toHaveAttribute() etc. without per-file imports.
 */
import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// findBy*/waitFor default to 1000ms, which flakes on async React Query flows
// when the full 46-file suite runs in parallel on a loaded machine. Keep the
// ceiling below vitest's 5s testTimeout so a single hung wait still produces
// a DOM dump instead of an opaque test-timeout.
configure({ asyncUtilTimeout: 3500 });

// jsdom has no ResizeObserver — recharts' <ResponsiveContainer> reads it on
// mount to size the chart. Without this stub, any component rendering a
// recharts chart throws "ResizeObserver is not defined" in every test run.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
