/**
 * Presence test for Vercel Web Analytics in the root layout (marketing
 * instrumentation, 2026-08-16 — see docs/BILLING_LAUNCH.md). Rendering the
 * full server layout to a DOM is heavy (fonts, ClerkProvider, theme
 * providers, nuqs adapter), so instead we call the async RootLayout function
 * directly and inspect the returned React element tree for <Analytics/> —
 * cheaper and just as conclusive, since we only need to prove it's mounted,
 * unconditionally, regardless of the Clerk feature flag.
 */
import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("@/components/layout/providers", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@clerk/nextjs", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@clerk/themes", () => ({ dark: {} }));
vi.mock("@/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@/components/themes/font.config", () => ({ fontVariables: "" }));
vi.mock("@/components/themes/theme.config", () => ({ DEFAULT_THEME: "dark" }));
vi.mock("@/components/themes/theme-provider", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/components/pwa/sw-register", () => ({ ServiceWorkerRegister: () => null }));
vi.mock("nextjs-toploader", () => ({ default: () => null }));
vi.mock("nuqs/adapters/next/app", () => ({
  NuqsAdapter: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/features/marketing/components/consent-prompt", () => ({ ConsentPrompt: () => null }));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function containsElementType(node: any, type: unknown): boolean {
  if (node === null || node === undefined || typeof node !== "object") return false;
  if (Array.isArray(node)) return node.some((child) => containsElementType(child, type));
  if (node.type === type) return true;
  return containsElementType(node.props?.children, type);
}

describe("RootLayout", () => {
  it("renders <Analytics /> unconditionally with Clerk disabled (no keys, default state)", async () => {
    vi.resetModules();
    vi.doMock("@/lib/billing/flags", () => ({ isClerkEnabled: () => false }));
    const { Analytics } = await import("@vercel/analytics/next");
    const RootLayout = (await import("../layout")).default;

    const tree = await RootLayout({ children: null });
    expect(containsElementType(tree, Analytics)).toBe(true);
  });

  it("still renders <Analytics /> with Clerk enabled", async () => {
    vi.resetModules();
    vi.doMock("@/lib/billing/flags", () => ({ isClerkEnabled: () => true }));
    const { Analytics } = await import("@vercel/analytics/next");
    const RootLayout = (await import("../layout")).default;

    const tree = await RootLayout({ children: null });
    expect(containsElementType(tree, Analytics)).toBe(true);
  });
});
