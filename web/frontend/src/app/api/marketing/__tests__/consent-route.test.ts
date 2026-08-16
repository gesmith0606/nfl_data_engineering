// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "../consent/route";
import { clerkClient, currentUser } from "@clerk/nextjs/server";

vi.mock("@clerk/nextjs/server", () => ({
  currentUser: vi.fn(),
  clerkClient: vi.fn(),
}));

const mockCurrentUser = vi.mocked(currentUser);
const mockClerkClient = vi.mocked(clerkClient);

const savedKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

const request = (body?: unknown) =>
  new Request("https://frontend-jet-seven-33.vercel.app/api/marketing/consent", {
    method: "POST",
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

describe("POST /api/marketing/consent", () => {
  const updateUserMetadata = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "pk_test_123";
    updateUserMetadata.mockResolvedValue(undefined);
    mockClerkClient.mockResolvedValue({
      users: { updateUserMetadata },
    } as never);
  });

  afterEach(() => {
    if (savedKey === undefined) delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    else process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = savedKey;
  });

  it("returns 503 when Clerk is not configured", async () => {
    delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    const res = await POST(request({ consent: true }));
    expect(res.status).toBe(503);
    expect(updateUserMetadata).not.toHaveBeenCalled();
  });

  it("returns 401 for signed-out users", async () => {
    mockCurrentUser.mockResolvedValue(null);
    const res = await POST(request({ consent: true }));
    expect(res.status).toBe(401);
    expect(updateUserMetadata).not.toHaveBeenCalled();
  });

  it("stamps publicMetadata.marketingConsent=true on opt-in", async () => {
    mockCurrentUser.mockResolvedValue({ id: "user_123" } as never);
    const res = await POST(request({ consent: true }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, consent: true });
    expect(updateUserMetadata).toHaveBeenCalledWith(
      "user_123",
      expect.objectContaining({
        publicMetadata: expect.objectContaining({ marketingConsent: true }),
      }),
    );
  });

  it("defaults to consent:false for a missing/malformed body (GDPR: no implicit opt-in)", async () => {
    mockCurrentUser.mockResolvedValue({ id: "user_123" } as never);
    const res = await POST(request());
    expect(res.status).toBe(200);
    expect(updateUserMetadata).toHaveBeenCalledWith(
      "user_123",
      expect.objectContaining({
        publicMetadata: expect.objectContaining({ marketingConsent: false }),
      }),
    );
  });

  it("returns 500 when the Clerk metadata write fails", async () => {
    mockCurrentUser.mockResolvedValue({ id: "user_123" } as never);
    updateUserMetadata.mockRejectedValue(new Error("clerk down"));
    const res = await POST(request({ consent: true }));
    expect(res.status).toBe(500);
  });
});
