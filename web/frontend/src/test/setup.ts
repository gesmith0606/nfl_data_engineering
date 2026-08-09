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
