import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

/**
 * Vitest configuration for the frontend.
 *
 * Added in Phase 70-01 to support unit tests for the shared <EmptyState />
 * component + any future component tests. Uses jsdom for DOM APIs and
 * includes testing-library matchers via src/test/setup.ts.
 *
 * Tests live alongside source under src/**\/__tests__ directories. The jsx
 * pragma is provided by @vitejs/plugin-react and follows Next.js's react-jsx
 * transform (no need for explicit React imports in test files).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['node_modules', '.next', 'dist']
  }
});
