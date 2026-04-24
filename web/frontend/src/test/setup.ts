/**
 * Vitest global setup — registers @testing-library/jest-dom matchers on the
 * global expect so individual test files can assert
 * .toBeInTheDocument() / .toHaveAttribute() etc. without per-file imports.
 */
import '@testing-library/jest-dom/vitest';
