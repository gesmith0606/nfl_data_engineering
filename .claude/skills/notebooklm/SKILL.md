---
name: notebooklm
description: Generate NFL content packages for NotebookLM — weekly podcasts, matchup breakdowns, and rankings summaries. Prepares sources, creates notebooks, and generates audio overviews.
---

# NotebookLM Content Generator

Generate NFL fantasy football content using Google NotebookLM for audio overviews (podcasts), summaries, and visual content.

## Setup

```bash
# Install (requires Python 3.10+, use system python if venv is 3.9)
pip install "notebooklm-py[browser]"
playwright install chromium

# Authenticate (opens browser for Google login)
notebooklm login

# If notebooklm-py fails on Python 3.9, use the manual workflow below
```

## Workflows

### 1. Weekly Podcast Content

Generate a weekly NFL fantasy podcast script from our projection data:

```bash
source venv/bin/activate
python scripts/generate_notebooklm_content.py --type weekly --week 1 --season 2026 --scoring half_ppr
```

This produces `output/notebooklm/weekly_w1_2026.md` containing:
- Top risers and fallers from projection changes
- Key matchup breakdowns (offense vs defense advantages)
- Start/sit recommendations with reasoning
- Injury impact analysis
- Waiver wire targets

Upload to NotebookLM and generate an Audio Overview.

### 2. Matchup Deep Dive

Generate a single-game matchup analysis:

```bash
python scripts/generate_notebooklm_content.py --type matchup --teams "KC vs BUF" --week 1
```

### 3. Rankings Summary

Generate a full rankings overview by position:

```bash
python scripts/generate_notebooklm_content.py --type rankings --scoring half_ppr
```

### 4. Manual NotebookLM Workflow

If the CLI tools aren't available:

1. Run the content generator script to produce markdown files
2. Go to https://notebooklm.google.com
3. Create a new notebook
4. Upload the generated markdown as a source
5. Click "Generate" on Audio Overview
6. Download the MP3
7. Upload to `web/frontend/public/podcasts/` for the website

### 5. Automated Pipeline (when notebooklm-py works)

```python
from notebooklm import NotebookLM

client = NotebookLM()

# Create notebook with NFL content
nb = client.create_notebook("NFL Week 1 - 2026")
nb.add_source(text=open("output/notebooklm/weekly_w1_2026.md").read())

# Generate audio overview
audio = nb.generate_audio_overview(style="SHORT")
audio.save("web/frontend/public/podcasts/week1_2026.mp3")
```

## Content Templates

The generator uses these templates:
- **Weekly**: Projection changes, matchups, start/sit, injuries, waivers
- **Matchup**: Team comparison, positional advantages, key players, game script prediction
- **Rankings**: Position-by-position tiers, risers/fallers, sleepers, busts
- **News**: Aggregated sentiment, trending players, team outlook changes

## Integration with Website

Generated content goes to:
- Audio: `web/frontend/public/podcasts/` (served as static files)
- Graphics: `web/frontend/public/graphics/`
- The news page can embed podcast players and graphic cards