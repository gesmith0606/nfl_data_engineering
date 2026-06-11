/**
 * Build-identity endpoint for the deploy live-gate.
 *
 * The deploy-web.yml `deploy-frontend` job polls this route after a push
 * and hard-fails if the live commit never converges on the pushed SHA —
 * closing the silent-drift failure mode where the Vercel webhook freezes
 * and production serves a weeks-old build (TD-09's Vercel-side twin,
 * observed as a 14-day-stale production on 2026-06-11).
 *
 * `VERCEL_GIT_COMMIT_SHA` is a Vercel system env var, present on
 * git-webhook deploys. CLI deploys from a local tree report 'unknown'
 * (the gate treats that as non-matching and keeps polling).
 */
export const dynamic = 'force-dynamic';

export async function GET() {
  return Response.json({
    commit: process.env.VERCEL_GIT_COMMIT_SHA ?? 'unknown',
    branch: process.env.VERCEL_GIT_COMMIT_REF ?? 'unknown',
    deploymentId: process.env.VERCEL_DEPLOYMENT_ID ?? null
  });
}
