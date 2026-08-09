'use client';

import { useRef, useEffect, useState } from 'react';
import PageContainer from '@/components/layout/page-container';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Icons } from '@/components/icons';
import { Gx01Head } from '@/components/gx01';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { WC_INPUT, WC_CTA_BUTTON, WC_OUTLINE_BUTTON } from '@/features/draft/utils/broadcast-ui';
import { usePersistentChat } from '@/hooks/use-persistent-chat';
import { FadeIn, PressScale } from '@/lib/motion-primitives';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types inferred from tool return shapes
// ---------------------------------------------------------------------------

interface ProjectionResult {
  found: boolean;
  message?: string;
  player_name?: string;
  team?: string;
  position?: string;
  projected_points?: number;
  projected_floor?: number;
  projected_ceiling?: number;
  injury_status?: string;
  scoring_format?: string;
  season?: number;
  week?: number;
}

interface CompareResult {
  found: boolean;
  message?: string;
  scoring_format?: string;
  season?: number;
  week?: number;
  player1?: PlayerSide;
  player2?: PlayerSide;
}

interface PlayerSide {
  name: string;
  team?: string;
  position?: string;
  projected_points?: number;
  floor?: number;
  ceiling?: number;
  injury_status?: string;
  error?: string;
}

interface SearchResult {
  found: boolean;
  message?: string;
  players?: Array<{
    player_id: string;
    player_name: string;
    team: string;
    position: string;
  }>;
}

interface NewsItem {
  title: string | null;
  source: string;
  published_at: string | null;
  player_name: string | null;
  team: string | null;
  body_snippet: string | null;
  sentiment: number | null;
  category: string | null;
  is_ruled_out: boolean;
  is_inactive: boolean;
  is_questionable: boolean;
  is_suspended: boolean;
  is_returning: boolean;
}

interface NewsFeedResult {
  found: boolean;
  message?: string;
  items?: NewsItem[];
}

// ---------------------------------------------------------------------------
// Suggestion chips shown in the empty state
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  'Who should I start at RB this week?',
  'Compare Patrick Mahomes vs Lamar Jackson',
  'Any injury news I should know about?',
  'Best waiver wire pickups this week?'
];

/** Conversational chip — same near-black/mint outline recipe as
 *  WC_OUTLINE_BUTTON minus the condensed-caps transform, since these render
 *  full sentences rather than short chrome labels. */
const SUGGESTION_CHIP =
  'rounded-full border-[rgba(145,237,208,0.3)] bg-transparent text-[#cfd6e4] hover:border-[var(--wc-mint,#91edd0)] hover:bg-[rgba(145,237,208,0.08)] hover:text-[var(--wc-mint,#91edd0)]';

// ---------------------------------------------------------------------------
// Tool result cards
// ---------------------------------------------------------------------------

function InjuryBadge({ status }: { status: string | undefined }) {
  if (!status || status === 'Active') return null;
  const variant =
    status === 'Out' || status === 'IR' ? 'destructive' : 'secondary';
  return <Badge variant={variant}>{status}</Badge>;
}

function ProjectionCard({ data }: { data: ProjectionResult }) {
  if (!data.found) {
    return (
      <BroadcastPanel
        rail={false}
        className='mt-[var(--space-2)] p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'
      >
        {data.message ?? 'Player not found.'}
      </BroadcastPanel>
    );
  }
  return (
    <BroadcastPanel className='mt-[var(--space-2)] p-[var(--space-4)]'>
      <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
        <span className='wc-display text-[length:var(--fs-sm)] font-semibold text-white'>
          {data.player_name}
        </span>
        <Badge
          variant='outline'
          className='border-white/20 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/70'
        >
          {data.position}
        </Badge>
        <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
          {data.team}
        </span>
        <InjuryBadge status={data.injury_status} />
      </div>
      <div className='mt-[var(--space-3)] flex gap-[var(--space-5)]'>
        <div>
          <div className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.1em] text-white/40 uppercase'>
            Projected
          </div>
          <div className='wc-num-hero !text-[length:var(--fs-h2)]'>
            {data.projected_points?.toFixed(1)}{' '}
            <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-normal text-white/40'>
              pts
            </span>
          </div>
        </div>
        <div>
          <div className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.1em] text-white/40 uppercase'>
            Floor
          </div>
          <div className='font-medium text-white/80'>
            {data.projected_floor?.toFixed(1)}
          </div>
        </div>
        <div>
          <div className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.1em] text-white/40 uppercase'>
            Ceiling
          </div>
          <div className='font-medium text-white/80'>
            {data.projected_ceiling?.toFixed(1)}
          </div>
        </div>
      </div>
      <p className='mt-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
        {data.scoring_format?.replace('_', '-').toUpperCase()} · Week{' '}
        {data.week}, {data.season}
      </p>
    </BroadcastPanel>
  );
}

function CompareCard({ data }: { data: CompareResult }) {
  if (!data.found) {
    return (
      <BroadcastPanel
        rail={false}
        className='mt-[var(--space-2)] p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'
      >
        {data.message ?? 'Comparison data not available.'}
      </BroadcastPanel>
    );
  }

  const renderSide = (player: PlayerSide | undefined, label: string) => {
    if (!player) return null;
    if (player.error) {
      return (
        <div className='flex-1 rounded-lg border border-white/10 p-[var(--space-3)]'>
          <p className='font-medium text-white'>{player.name}</p>
          <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
            {player.error}
          </p>
        </div>
      );
    }
    return (
      <div className='flex-1 rounded-lg border border-white/10 p-[var(--space-3)]'>
        <div className='mb-[var(--space-1)] flex items-center gap-[var(--space-1)]'>
          <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
            {label}
          </span>
          <Badge
            variant='outline'
            className='border-white/20 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/70'
          >
            {player.position}
          </Badge>
          <InjuryBadge status={player.injury_status} />
        </div>
        <p className='font-semibold text-white'>{player.name}</p>
        <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
          {player.team}
        </p>
        <p className='mt-[var(--space-2)] wc-num-hero !text-[length:var(--fs-h2)]'>
          {player.projected_points?.toFixed(1)}{' '}
          <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-normal text-white/40'>
            pts
          </span>
        </p>
        <div className='mt-[var(--space-1)] flex gap-[var(--space-3)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
          <span>Floor: {player.floor?.toFixed(1)}</span>
          <span>Ceil: {player.ceiling?.toFixed(1)}</span>
        </div>
      </div>
    );
  };

  return (
    <BroadcastPanel className='mt-[var(--space-2)] p-[var(--space-4)]'>
      <p className='wc-display text-[length:var(--fs-sm)] font-semibold text-white'>
        Start/Sit Comparison ·{' '}
        {data.scoring_format?.replace('_', '-').toUpperCase()} · Week{' '}
        {data.week}
      </p>
      <div className='mt-[var(--space-3)] flex gap-[var(--space-3)]'>
        {renderSide(data.player1, 'Player 1')}
        {renderSide(data.player2, 'Player 2')}
      </div>
    </BroadcastPanel>
  );
}

function SearchCard({ data }: { data: SearchResult }) {
  if (!data.found || !data.players?.length) {
    return (
      <BroadcastPanel
        rail={false}
        className='mt-[var(--space-2)] p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'
      >
        {data.message ?? 'No players found.'}
      </BroadcastPanel>
    );
  }
  return (
    <BroadcastPanel rail={false} className='mt-[var(--space-2)] p-[var(--space-3)]'>
      <div className='flex flex-wrap gap-[var(--space-2)]'>
        {data.players.map((p) => (
          <div
            key={p.player_id}
            className='flex items-center gap-[var(--space-1)] rounded-md border border-white/15 px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/80'
          >
            <Badge
              variant='outline'
              className='border-white/20 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/70'
            >
              {p.position}
            </Badge>
            <span className='font-medium text-white'>{p.player_name}</span>
            <span className='text-white/40'>{p.team}</span>
          </div>
        ))}
      </div>
    </BroadcastPanel>
  );
}

function SentimentDot({ score }: { score: number | null }) {
  if (score === null) return null;
  const color =
    score > 0.1
      ? 'bg-[var(--wc-pos,#0eaf7d)]'
      : score < -0.1
        ? 'bg-[var(--wc-neg,#ef4444)]'
        : 'bg-[var(--wc-yellow,#ffd84d)]';
  const label = score > 0.1 ? 'Positive' : score < -0.1 ? 'Negative' : 'Neutral';
  return (
    <span
      title={`Sentiment: ${label} (${score.toFixed(2)})`}
      className={`inline-block h-2 w-2 rounded-full ${color} shrink-0 mt-1.5`}
    />
  );
}

function NewsCard({ data }: { data: NewsFeedResult }) {
  if (!data.found || !data.items?.length) {
    return (
      <BroadcastPanel
        rail={false}
        className='mt-[var(--space-2)] p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'
      >
        {data.message ?? 'No news available.'}
      </BroadcastPanel>
    );
  }
  return (
    <BroadcastPanel rail={false} className='mt-[var(--space-2)] divide-y divide-white/10 p-0'>
      {data.items.slice(0, 5).map((item, i) => (
        <div key={i} className='px-[var(--space-3)] py-[var(--space-2)]'>
          <div className='flex items-start justify-between gap-[var(--space-2)]'>
            <div className='flex min-w-0 items-start gap-[var(--space-2)]'>
              <SentimentDot score={item.sentiment} />
              <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium text-white/90'>
                {item.title ?? item.body_snippet ?? 'Untitled'}
              </p>
            </div>
            <div className='flex shrink-0 gap-[var(--space-1)]'>
              {item.is_ruled_out && (
                <Badge
                  variant='destructive'
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
                >
                  OUT
                </Badge>
              )}
              {item.is_inactive && !item.is_ruled_out && (
                <Badge
                  variant='destructive'
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
                >
                  INACTIVE
                </Badge>
              )}
              {item.is_suspended && (
                <Badge
                  variant='destructive'
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
                >
                  SUSP
                </Badge>
              )}
              {item.is_questionable && !item.is_ruled_out && !item.is_inactive && (
                <Badge
                  variant='secondary'
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
                >
                  Q
                </Badge>
              )}
              {item.is_returning && (
                <Badge
                  variant='outline'
                  className='border-[var(--wc-pos,#0eaf7d)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-[var(--wc-pos,#0eaf7d)]'
                >
                  RTN
                </Badge>
              )}
            </div>
          </div>
          <div className='mt-0.5 flex items-center gap-[var(--space-2)]'>
            {item.player_name && (
              <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
                {item.player_name}
                {item.team ? ` · ${item.team}` : ''}
              </p>
            )}
            {item.category && (
              <Badge
                variant='outline'
                className='h-[var(--space-4)] border-white/20 px-[var(--space-1)] py-0 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/60'
              >
                {item.category}
              </Badge>
            )}
          </div>
        </div>
      ))}
    </BroadcastPanel>
  );
}

// ---------------------------------------------------------------------------
// Main advisor page
// ---------------------------------------------------------------------------

export default function AdvisorPage() {
  const [input, setInput] = useState('');
  const [lastUserMessage, setLastUserMessage] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const { messages, sendMessage, status, error, clear } = usePersistentChat();

  const isLoading = status === 'streaming' || status === 'submitted';
  const hasError = status === 'error' || !!error;

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;
    setLastUserMessage(text);
    sendMessage({ text });
    setInput('');
  }

  function handleSuggestion(text: string) {
    if (isLoading) return;
    setLastUserMessage(text);
    sendMessage({ text });
  }

  function handleRetry() {
    if (!lastUserMessage || isLoading) return;
    sendMessage({ text: lastUserMessage });
  }

  return (
    <PageContainer
      pageTitle='AI Fantasy Advisor'
      pageDescription='Ask about start/sit decisions, trade analysis, waiver wire pickups, and more'
    >
      {/* Mobile: use the full-ish viewport (more vertical room than 100dvh-160).
       *  Desktop: preserve the original 160px reserve for header + padding. */}
      <FadeIn className='flex h-[calc(100dvh-var(--size-header)-var(--space-8))] flex-col gap-[var(--space-3)] md:h-[calc(100dvh-160px)]'>
        {/* Top action bar — visible only when a conversation exists */}
        {messages.length > 0 && (
          <div className='flex justify-end'>
            <PressScale>
              <Button
                variant='outline'
                size='sm'
                className={cn(WC_OUTLINE_BUTTON, 'text-[length:var(--fs-xs)] leading-[var(--lh-xs)]')}
                onClick={clear}
              >
                <Icons.trash className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                Clear conversation
              </Button>
            </PressScale>
          </div>
        )}

        {/* Chat panel — near-black broadcast surface, GX-01 header (chat-widget
            convention scaled up to a full page surface). */}
        <div
          className='flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[rgba(145,237,208,0.25)]'
          style={{ background: 'var(--wc-bar,#05070d)' }}
        >
          {/* Yellow condensed header */}
          <div className='flex shrink-0 items-center gap-[var(--space-3)] border-b border-[rgba(145,237,208,0.2)] px-[var(--space-4)] py-[var(--space-3)]'>
            <div
              className='flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[rgba(255,216,77,0.4)]'
              style={{ background: 'var(--wc-bar,#05070d)' }}
            >
              <Gx01Head className='scale-90' />
            </div>
            <div>
              <h2
                className='wc-display text-[length:var(--fs-sm)] leading-none tracking-[0.14em]'
                style={{ color: 'var(--wc-yellow,#ffd84d)' }}
              >
                Advisor // GX-01
              </h2>
              <p className='mt-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/50'>
                Fantasy football assistant
              </p>
            </div>
          </div>

          {/* Message area */}
          <ScrollArea className='min-h-0 flex-1'>
            <div className='flex flex-col gap-[var(--gap-stack)] p-[var(--pad-card)]'>
              {messages.length === 0 && (
                <div className='flex flex-col items-center justify-center py-16 text-center'>
                  <div
                    className='mb-[var(--space-4)] rounded-full p-[var(--space-4)]'
                    style={{ background: 'rgba(145,237,208,0.12)' }}
                  >
                    <Icons.sparkles
                      className='h-[var(--space-8)] w-[var(--space-8)]'
                      style={{ color: 'var(--wc-mint,#91edd0)' }}
                    />
                  </div>
                  <h2 className='wc-display mb-[var(--space-1)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)] text-white'>
                    Your AI Fantasy Advisor
                  </h2>
                  <p className='mb-[var(--space-6)] max-w-sm text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'>
                    Ask me about start/sit decisions, trade analysis, waiver wire
                    pickups, or player projections.
                  </p>
                  <div className='flex flex-wrap justify-center gap-[var(--space-2)]'>
                    {SUGGESTIONS.map((s) => (
                      <PressScale key={s}>
                        <Button
                          variant='outline'
                          size='sm'
                          className={cn(SUGGESTION_CHIP, 'text-[length:var(--fs-xs)] leading-[var(--lh-xs)]')}
                          onClick={() => handleSuggestion(s)}
                        >
                          {s}
                        </Button>
                      </PressScale>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message) => {
                const isUser = message.role === 'user';
                return (
                  <div
                    key={message.id}
                    className={`flex gap-[var(--space-3)] ${isUser ? 'flex-row-reverse' : ''}`}
                  >
                    <Avatar className='h-[var(--space-8)] w-[var(--space-8)] shrink-0'>
                      <AvatarFallback
                        className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                        style={
                          isUser
                            ? { background: 'rgba(91,103,199,0.3)', color: '#c7cdf5' }
                            : { background: 'rgba(145,237,208,0.15)', color: 'var(--wc-mint,#91edd0)' }
                        }
                      >
                        {isUser ? 'You' : 'AI'}
                      </AvatarFallback>
                    </Avatar>

                    <div
                      className={`flex max-w-[85%] flex-col gap-[var(--space-1)] sm:max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}
                    >
                      {message.parts.map((part, partIndex) => {
                        switch (part.type) {
                          case 'text':
                            return (
                              <div
                                key={partIndex}
                                className={`rounded-2xl px-[var(--space-4)] py-[var(--space-2)] text-[length:var(--fs-sm)] leading-relaxed whitespace-pre-wrap ${
                                  isUser
                                    ? 'rounded-tr-sm text-white'
                                    : 'rounded-tl-sm border border-white/10 text-white/85'
                                }`}
                                style={
                                  isUser
                                    ? { background: 'var(--wc-peri,#5b67c7)' }
                                    : { background: 'rgba(255,255,255,0.06)' }
                                }
                              >
                                {part.text}
                              </div>
                            );

                          case 'tool-getPlayerProjection':
                            if (part.state === 'output-available') {
                              return (
                                <ProjectionCard
                                  key={partIndex}
                                  data={part.output as ProjectionResult}
                                />
                              );
                            }
                            if (
                              part.state === 'input-streaming' ||
                              part.state === 'input-available'
                            ) {
                              return (
                                <div
                                  key={partIndex}
                                  className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'
                                >
                                  <Icons.spinner className='h-[var(--space-3)] w-[var(--space-3)] animate-spin' />
                                  Looking up projection...
                                </div>
                              );
                            }
                            return null;

                          case 'tool-compareStartSit':
                            if (part.state === 'output-available') {
                              return (
                                <CompareCard
                                  key={partIndex}
                                  data={part.output as CompareResult}
                                />
                              );
                            }
                            if (
                              part.state === 'input-streaming' ||
                              part.state === 'input-available'
                            ) {
                              return (
                                <div
                                  key={partIndex}
                                  className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'
                                >
                                  <Icons.spinner className='h-[var(--space-3)] w-[var(--space-3)] animate-spin' />
                                  Comparing players...
                                </div>
                              );
                            }
                            return null;

                          case 'tool-searchPlayers':
                            if (part.state === 'output-available') {
                              return (
                                <SearchCard
                                  key={partIndex}
                                  data={part.output as SearchResult}
                                />
                              );
                            }
                            if (
                              part.state === 'input-streaming' ||
                              part.state === 'input-available'
                            ) {
                              return (
                                <div
                                  key={partIndex}
                                  className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'
                                >
                                  <Icons.spinner className='h-[var(--space-3)] w-[var(--space-3)] animate-spin' />
                                  Searching players...
                                </div>
                              );
                            }
                            return null;

                          case 'tool-getNewsFeed':
                            if (part.state === 'output-available') {
                              return (
                                <NewsCard
                                  key={partIndex}
                                  data={part.output as NewsFeedResult}
                                />
                              );
                            }
                            if (
                              part.state === 'input-streaming' ||
                              part.state === 'input-available'
                            ) {
                              return (
                                <div
                                  key={partIndex}
                                  className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'
                                >
                                  <Icons.spinner className='h-[var(--space-3)] w-[var(--space-3)] animate-spin' />
                                  Fetching news...
                                </div>
                              );
                            }
                            return null;

                          default:
                            return null;
                        }
                      })}
                    </div>
                  </div>
                );
              })}

              {/* Typing indicator when AI is generating */}
              {isLoading && (
                <div className='flex gap-[var(--space-3)]'>
                  <Avatar className='h-[var(--space-8)] w-[var(--space-8)] shrink-0'>
                    <AvatarFallback
                      className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                      style={{ background: 'rgba(145,237,208,0.15)', color: 'var(--wc-mint,#91edd0)' }}
                    >
                      AI
                    </AvatarFallback>
                  </Avatar>
                  <div
                    className='flex items-center gap-[var(--space-1)] rounded-2xl rounded-tl-sm border border-white/10 px-[var(--space-4)] py-[var(--space-3)]'
                    style={{ background: 'rgba(255,255,255,0.06)' }}
                  >
                    <span className='h-1.5 w-1.5 animate-bounce rounded-full bg-white/40 [animation-delay:0ms]' />
                    <span className='h-1.5 w-1.5 animate-bounce rounded-full bg-white/40 [animation-delay:150ms]' />
                    <span className='h-1.5 w-1.5 animate-bounce rounded-full bg-white/40 [animation-delay:300ms]' />
                  </div>
                </div>
              )}

              {/* Error state with retry */}
              {hasError && (
                <div className='flex gap-[var(--space-3)]'>
                  <Avatar className='h-[var(--space-8)] w-[var(--space-8)] shrink-0'>
                    <AvatarFallback
                      className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                      style={{ background: 'rgba(145,237,208,0.15)', color: 'var(--wc-mint,#91edd0)' }}
                    >
                      AI
                    </AvatarFallback>
                  </Avatar>
                  <div
                    className='flex flex-col gap-[var(--space-2)] rounded-2xl rounded-tl-sm border px-[var(--space-4)] py-[var(--space-3)]'
                    style={{
                      background: 'rgba(239,68,68,0.1)',
                      borderColor: 'rgba(239,68,68,0.35)'
                    }}
                  >
                    <p
                      className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'
                      style={{ color: '#ff9d9d' }}
                    >
                      Something went wrong. This may be a temporary issue with the AI
                      provider or the data backend.
                    </p>
                    {lastUserMessage && (
                      <PressScale className='self-start'>
                        <Button
                          variant='outline'
                          size='sm'
                          className={cn(WC_OUTLINE_BUTTON, 'text-[length:var(--fs-xs)] leading-[var(--lh-xs)]')}
                          onClick={handleRetry}
                          disabled={isLoading}
                        >
                          <Icons.spinner
                            className={`mr-1.5 h-[var(--space-3)] w-[var(--space-3)] ${isLoading ? 'animate-spin' : 'hidden'}`}
                          />
                          Retry
                        </Button>
                      </PressScale>
                    )}
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </ScrollArea>

          {/* Input form — tap targets ≥ 44px on mobile, dark surface + mint focus. */}
          <form
            onSubmit={handleSubmit}
            className='flex shrink-0 gap-[var(--space-2)] border-t border-[rgba(145,237,208,0.2)] p-[var(--space-3)]'
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder='Ask about start/sit, trades, waiver wire...'
              disabled={isLoading}
              className={cn(WC_INPUT, 'h-[var(--tap-min)] flex-1 sm:h-9')}
            />
            <PressScale>
              <Button
                type='submit'
                disabled={isLoading || !input.trim()}
                className={cn(WC_CTA_BUTTON, 'h-[var(--tap-min)] sm:h-9')}
              >
                {isLoading ? (
                  <Icons.spinner className='h-[var(--space-4)] w-[var(--space-4)] animate-spin' />
                ) : (
                  <Icons.send className='h-[var(--space-4)] w-[var(--space-4)]' />
                )}
                <span className='ml-[var(--space-2)] hidden sm:inline'>Send</span>
              </Button>
            </PressScale>
          </form>
        </div>
      </FadeIn>
    </PageContainer>
  );
}
