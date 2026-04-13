# AI Fantasy Advisor — Research Summary

**Researched:** 2026-04-12
**Confidence:** HIGH

## Recommended Stack

**Gemini 2.5 Flash (free tier)** + **Groq Llama 8B (fallback)** + **Vercel AI SDK v6** + **tool-calling to FastAPI**

## Why This Works

- Tool-calling beats RAG — our data is structured and behind APIs, not in documents
- Free tier covers 100-500 daily users at $0/month
- Vercel AI SDK is native to our Next.js stack
- Provider fallback (Gemini → Groq) handles rate limits automatically

## Cost

| Daily Users | Monthly Cost |
|-------------|-------------|
| 100-500 | $0 (free tiers) |
| 1,000 | ~$5/month |
| 5,000 | ~$20/month |

## Architecture

```
useChat() → Next.js API route → streamText() + tools → FastAPI endpoints → data
```

4 core tools:
1. `getPlayerProjection` — lookup player projections
2. `compareStartSit` — compare two players head-to-head
3. `searchPlayers` — find players by name
4. `getNewsFeed` — latest news/injury updates

## Implementation Phases

1. Foundation — AI SDK setup, Gemini provider, basic chat UI
2. Tool definitions — wire 4 tools to FastAPI endpoints
3. Prompt engineering — system prompt with fantasy expertise
4. Rate limit management — provider fallback, caching, usage tracking

## Required API Keys (free)

- `GOOGLE_GENERATIVE_AI_API_KEY` — free from ai.google.dev
- `GROQ_API_KEY` — free from console.groq.com

## Full Research

See agent output for detailed STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md with code examples.
