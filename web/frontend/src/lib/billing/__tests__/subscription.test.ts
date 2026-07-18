import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getSubscriptionStatus } from '../subscription';
import { currentUser } from '@clerk/nextjs/server';

vi.mock('@clerk/nextjs/server', () => ({
  currentUser: vi.fn()
}));

const mockCurrentUser = vi.mocked(currentUser);

describe('getSubscriptionStatus (server-side entitlement)', () => {
  const originalKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = 'pk_test_123';
  });

  afterEach(() => {
    if (originalKey === undefined) {
      delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    } else {
      process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = originalKey;
    }
  });

  it('grants access with billing disabled and never calls Clerk', async () => {
    delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    const status = await getSubscriptionStatus();
    expect(status).toEqual({
      billingEnabled: false,
      signedIn: false,
      premium: false,
      hasAccess: true
    });
    expect(mockCurrentUser).not.toHaveBeenCalled();
  });

  it('denies anonymous sessions when billing is enabled', async () => {
    mockCurrentUser.mockResolvedValue(null);
    const status = await getSubscriptionStatus();
    expect(status.billingEnabled).toBe(true);
    expect(status.signedIn).toBe(false);
    expect(status.hasAccess).toBe(false);
  });

  it('denies signed-in users without the premium stamp', async () => {
    mockCurrentUser.mockResolvedValue({ publicMetadata: {} } as never);
    const status = await getSubscriptionStatus();
    expect(status.signedIn).toBe(true);
    expect(status.premium).toBe(false);
    expect(status.hasAccess).toBe(false);
  });

  it('grants signed-in users with premium: true in publicMetadata', async () => {
    mockCurrentUser.mockResolvedValue({ publicMetadata: { premium: true } } as never);
    const status = await getSubscriptionStatus();
    expect(status.premium).toBe(true);
    expect(status.hasAccess).toBe(true);
  });

  it('rejects truthy-but-not-boolean premium values', async () => {
    mockCurrentUser.mockResolvedValue({ publicMetadata: { premium: 'yes' } } as never);
    const status = await getSubscriptionStatus();
    expect(status.premium).toBe(false);
    expect(status.hasAccess).toBe(false);
  });

  it('treats Clerk errors as signed out instead of crashing the page', async () => {
    mockCurrentUser.mockRejectedValue(new Error('clerk half-configured'));
    const status = await getSubscriptionStatus();
    expect(status).toEqual({
      billingEnabled: true,
      signedIn: false,
      premium: false,
      hasAccess: false
    });
  });
});
