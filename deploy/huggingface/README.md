---
title: NFL Data Engineering API
emoji: 🏈
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: FastAPI backend (bridge) for the NFL fantasy + game-prediction site
---

# NFL Data Engineering API — bridge backend

FastAPI backend serving fantasy projections, game predictions, player/lineup
queries, and news/sentiment for the NFL data-engineering site frontend.

Runs in **Parquet-fallback mode**: the API reads committed Parquet from the
cloned source repo (no live database). The Dockerfile shallow-clones the
public source repo at build time, so this Space stays minimal and always
builds from the latest `main`.

- Health: `/api/health`
- Source: https://github.com/gesmith0606/nfl_data_engineering

> ⚠️ **This is a temporary bridge**, stood up after the Railway trial lapsed.
> It is not the public-launch backend. Phase 84 (Deploy Hardening) moves the
> data out of the image and onto a launch-grade host before the public launch.
>
> To refresh data: bump `CACHE_BUST` in the Dockerfile (forces a re-clone of
> the latest `main`), then the Space rebuilds.
