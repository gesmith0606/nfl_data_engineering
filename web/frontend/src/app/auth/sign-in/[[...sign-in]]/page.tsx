import { SignIn } from '@clerk/nextjs';
import { redirect } from 'next/navigation';
import { isClerkEnabled } from '@/lib/billing/flags';

export const dynamic = 'force-dynamic';

export const metadata = { title: 'Sign In' };

/** Clerk sign-in. Feature-flagged: without keys this route redirects home. */
export default function SignInPage() {
  if (!isClerkEnabled()) redirect('/');

  return (
    <div className='flex min-h-screen items-center justify-center bg-[var(--wc-stadium,#070a12)] px-4 py-12'>
      <SignIn />
    </div>
  );
}
