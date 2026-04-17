'use client';

import { useState } from 'react';
import PageContainer from '@/components/layout/page-container';
import { NewsFeed } from '@/features/nfl/components/news-feed';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';

/**
 * News and Sentiment dashboard page.
 *
 * Displays NFL news from multiple sources (ESPN, Reddit, Sleeper, PFF) with
 * sentiment analysis. Includes:
 * - Overview: summary stats, top movers, alerts, team outlook
 * - News Feed: scrollable articles with source and search filters
 * - Team Sentiment: per-team sentiment grid and detail table
 * - Player Signals: bullish/bearish/neutral breakdown per player
 */
export default function NewsPage() {
  const [season, setSeason] = useState(2025);
  const [week, setWeek] = useState<number | undefined>(1);

  return (
    <PageContainer
      scrollable
      pageTitle='News & Sentiment'
      pageDescription='NFL news, sentiment signals, and player/team outlook from all sources'
    >
      <div className='space-y-4'>
        {/* Season / week selectors */}
        <div className='flex flex-wrap items-center gap-3'>
          <Select
            value={String(season)}
            onValueChange={(v) => setSeason(Number(v))}
          >
            <SelectTrigger className='w-28'>
              <SelectValue placeholder='Season' />
            </SelectTrigger>
            <SelectContent>
              {[2026, 2025, 2024, 2023, 2022].map((s) => (
                <SelectItem key={s} value={String(s)}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={week !== undefined ? String(week) : 'all'}
            onValueChange={(v) =>
              setWeek(v === 'all' ? undefined : Number(v))
            }
          >
            <SelectTrigger className='w-28'>
              <SelectValue placeholder='Week' />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All weeks</SelectItem>
              {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
                <SelectItem key={w} value={String(w)}>
                  Week {w}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <NewsFeed season={season} week={week} />
      </div>
    </PageContainer>
  );
}
