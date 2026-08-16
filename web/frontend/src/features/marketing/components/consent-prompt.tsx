"use client";

import { useState } from "react";
import { useUser } from "@clerk/nextjs";
import { cn } from "@/lib/utils";

/**
 * One-time post-signup marketing-consent banner. Clerk's prebuilt <SignUp/>
 * has no supported custom-field slot for a checkbox without rebuilding the
 * whole form from Clerk Elements primitives — far more code for the same
 * outcome — so consent is captured just after sign-up instead, the first
 * time the user shows up with `publicMetadata.marketingConsent` unset.
 *
 * Default is UNCHECKED (GDPR: no pre-ticked consent boxes). Dismissing
 * without checking records an explicit opt-out so the prompt never nags
 * again. Writes land on Clerk metadata via POST /api/marketing/consent,
 * guarded server-side by `currentUser()`.
 */
export function ConsentPrompt({ className }: { className?: string }) {
  const { isLoaded, isSignedIn, user } = useUser();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(false);

  if (!isLoaded || !isSignedIn || hidden) return null;
  // Already decided (either direction) — never show twice.
  if (user.publicMetadata?.marketingConsent !== undefined) return null;

  async function submit(consent: boolean) {
    setBusy(true);
    try {
      await fetch("/api/marketing/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ consent }),
      });
      await user?.reload();
    } finally {
      setBusy(false);
      setHidden(true);
    }
  }

  return (
    <div
      role="status"
      className={cn(
        "fixed bottom-4 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-md -translate-x-1/2 items-center gap-3 rounded-xl border border-white/10 bg-[var(--wc-bar-hi,#131722)] px-4 py-3 shadow-lg sm:left-auto sm:right-4 sm:translate-x-0",
        className,
      )}
    >
      <label className="flex flex-1 items-start gap-2 text-sm text-[#cfd6e4]">
        <input
          type="checkbox"
          checked={checked}
          disabled={busy}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-white/20 bg-transparent"
        />
        <span>Send me product updates &amp; fantasy insights (optional)</span>
      </label>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => submit(checked)}
          className="wc-display rounded-full bg-[var(--wc-peri,#5b67c7)] px-3 py-1.5 text-[12px] tracking-[0.1em] text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          Save
        </button>
        <button
          type="button"
          aria-label="Dismiss"
          disabled={busy}
          onClick={() => submit(false)}
          className="text-[#9aa3b8] transition-colors hover:text-white"
        >
          ×
        </button>
      </div>
    </div>
  );
}
