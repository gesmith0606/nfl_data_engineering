# HF Spaces Migration Runbook (bridge backend)

Restores production after the Railway trial lapsed (~2026-05-06). Free, no
custom domain, sleeps on inactivity — acceptable for a private beta bridge,
**not** the public-launch backend (see Phase 84).

## What you do (one-time, ~3 min)

1. Have a Hugging Face account (free): https://huggingface.co/join
2. Create a **write** access token: https://huggingface.co/settings/tokens
   → "New token" → type **Write** → copy it.
3. In this session run (keeps the token out of chat history):

   ```
   ! venv/bin/hf auth login
   ```

   Paste the token when prompted. (Or: `! export HF_TOKEN=hf_xxx`.)
4. Tell me your HF **username** and the **Space name** you want
   (default suggestion: `nfl-data-api`).

## What I do (automated once token + name are set)

1. Create the Space:
   `hf repo create <user>/<space> --repo-type space --space_sdk docker`
2. Push `deploy/huggingface/Dockerfile` + `README.md` to the Space repo
   (uploaded as `Dockerfile` and `README.md` at the Space root).
3. Watch the build; smoke-test `https://<user>-<space>.hf.space/api/health`
   and the core endpoints against the sanity gate.

## Frontend repoint (env var — NOT a code change)

`next.config.ts` rewrites `/api/*` → `${NEXT_PUBLIC_API_URL}`. Currently the
Railway URL. After the Space is verified:

- **Vercel (production):** set project env var
  `NEXT_PUBLIC_API_URL = https://<user>-<space>.hf.space`
  (Vercel dashboard → project `prj_cMbOuGglblPI03KHGb0CYu5lQl5J` → Settings
  → Environment Variables, Production scope), then redeploy the frontend.
  CLI equivalent: `vercel env rm NEXT_PUBLIC_API_URL production` then
  `vercel env add NEXT_PUBLIC_API_URL production` → `vercel --prod`.
- **Local parity:** update `web/frontend/.env.production.local`
  (gitignored, local-only) to the same URL.

No CORS change needed: the browser hits the Vercel domain; Vercel proxies
server-side to the backend via the Next rewrite.

## Known bridge limitations (tracked for Phase 84)

- Sleeps after ~48h idle → cold start for the first visitor.
- No custom domain / rate limiting / WAF.
- `ANTHROPIC_API_KEY` not set → AI advisor/chat degraded (pre-existing;
  add it as a Space **secret** if the advisor must be live in the beta).
- Build re-clones the repo; refresh data by bumping `CACHE_BUST`.
