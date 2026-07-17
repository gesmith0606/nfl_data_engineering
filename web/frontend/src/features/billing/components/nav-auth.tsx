'use client';

import Link from 'next/link';
import { SignedIn, SignedOut, UserButton } from '@clerk/nextjs';

/**
 * Auth controls for the broadcast nav. Feature-flagged: renders nothing when
 * Clerk is not configured, so the nav is unchanged until keys exist.
 * (NEXT_PUBLIC_* env is inlined at build time, so this check is safe in a
 * client component.)
 */
const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export function NavAuth() {
  if (!clerkEnabled) return null;

  return (
    <div className='flex items-center gap-4'>
      <SignedOut>
        <Link
          href='/auth/sign-in'
          className='wc-display whitespace-nowrap text-[15px] tracking-[0.1em] text-[#cfd6e4] transition-colors hover:text-[var(--wc-mint,#91edd0)]'
        >
          Sign In
        </Link>
        <Link
          href='/pricing'
          className='wc-display hidden whitespace-nowrap rounded-full bg-[var(--wc-peri,#5b67c7)] px-4 py-1 text-[13px] tracking-[0.1em] text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)] sm:block'
        >
          Go Premium
        </Link>
      </SignedOut>
      <SignedIn>
        <UserButton
          appearance={{
            elements: { userButtonAvatarBox: 'h-8 w-8' }
          }}
        />
      </SignedIn>
    </div>
  );
}
