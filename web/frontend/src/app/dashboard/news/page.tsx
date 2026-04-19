'use client';

import { useState } from 'react';
import PageContainer from '@/components/layout/page-container';
import { NewsFeed } from '@/features/nfl/components/news-feed';
import { TeamEventDensityGrid } from '@/features/nfl/components/TeamEventDensityGrid';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Icons } from '@/components/icons';

/**
 * News and Sentiment dashboard page.
 *
 * Displays NFL news from multiple sources (ESPN, Reddit, Sleeper, RotoWire,
 * PFT, Sleeper, Twitter) with rule-extracted structured event flags:
 * - Team Event Density grid (NEWS-03): 32-team grid keyed off event counts
 * - News Feed: scrollable articles with source and search filters
 * - Team Sentiment (legacy): signal-based positive/neutral/negative grid
 * - Player Signals: bullish/bearish/neutral breakdown per player
 */
export default function NewsPage() {
  const [season, setSeason] = useState(2025);
  const [week, setWeek] = useState<number | undefined>(1);

  // The event grid needs a concrete week — default to 1 when the user
  // has selected "all weeks" on the feed.
  const eventsWeek = week ?? 1;

  return (
    <PageContainer
      scrollable
      pageTitle='News & Sentiment'
      pageDescription='NFL news, rule-extracted event signals, and player/team outlook from all sources'
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

        {/* Team event density grid (NEWS-03) */}
        <Card>
          <CardHeader>
            <CardTitle className='flex items-center gap-2 text-base'>
              <Icons.shield className='h-4 w-4' />
              Team Event Density
            </CardTitle>
            <CardDescription>
              All 32 teams, colored by rule-extracted event density for week{' '}
              {eventsWeek}. Click a team to filter the news feed below.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TeamEventDensityGrid season={season} week={eventsWeek} />
          </CardContent>
        </Card>

        <NewsFeed season={season} week={week} />
      </div>
    </PageContainer>
  );
}
