'use client';

import { useRef, useEffect, useState } from 'react';
import PageContainer from '@/components/layout/page-container';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Icons } from '@/components/icons';
import { usePersistentChat } from '@/hooks/use-persistent-chat';
import { FadeIn, PressScale } from '@/lib/motion-primitives';

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
      <Card className='border-muted bg-muted/30 mt-[var(--space-2)]'>
        <CardContent className='p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          {data.message ?? 'Player not found.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-primary/20 bg-primary/5 mt-[var(--space-2)]'>
      <CardHeader className='pb-[var(--space-1)] pt-[var(--space-3)]'>
        <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
          {data.player_name}
          <Badge
            variant='outline'
            className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
          >
            {data.position}
          </Badge>
          <span className='text-muted-foreground font-normal'>{data.team}</span>
          <InjuryBadge status={data.injury_status} />
        </CardTitle>
      </CardHeader>
      <CardContent className='pb-[var(--space-3)]'>
        <div className='flex gap-[var(--space-4)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          <div>
            <span className='text-muted-foreground'>Projected</span>
            <p className='font-bold text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
              {data.projected_points?.toFixed(1)} pts
            </p>
          </div>
          <div>
            <span className='text-muted-foreground'>Floor</span>
            <p className='font-medium'>{data.projected_floor?.toFixed(1)}</p>
          </div>
          <div>
            <span className='text-muted-foreground'>Ceiling</span>
            <p className='font-medium'>{data.projected_ceiling?.toFixed(1)}</p>
          </div>
        </div>
        <p className='text-muted-foreground mt-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          {data.scoring_format?.replace('_', '-').toUpperCase()} · Week{' '}
          {data.week}, {data.season}
        </p>
      </CardContent>
    </Card>
  );
}

function CompareCard({ data }: { data: CompareResult }) {
  if (!data.found) {
    return (
      <Card className='border-muted bg-muted/30 mt-2'>
        <CardContent className='p-3 text-sm text-muted-foreground'>
          {data.message ?? 'Comparison data not available.'}
        </CardContent>
      </Card>
    );
  }

  const renderSide = (player: PlayerSide | undefined, label: string) => {
    if (!player) return null;
    if (player.error) {
      return (
        <div className='flex-1 rounded-lg border p-[var(--space-3)]'>
          <p className='font-medium'>{player.name}</p>
          <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            {player.error}
          </p>
        </div>
      );
    }
    return (
      <div className='flex-1 rounded-lg border p-[var(--space-3)]'>
        <div className='mb-[var(--space-1)] flex items-center gap-[var(--space-1)]'>
          <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
            {label}
          </span>
          <Badge
            variant='outline'
            className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
          >
            {player.position}
          </Badge>
          <InjuryBadge status={player.injury_status} />
        </div>
        <p className='font-semibold'>{player.name}</p>
        <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          {player.team}
        </p>
        <p className='mt-[var(--space-2)] text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-bold'>
          {player.projected_points?.toFixed(1)}{' '}
          <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-normal text-muted-foreground'>
            pts
          </span>
        </p>
        <div className='mt-[var(--space-1)] flex gap-[var(--space-3)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
          <span>Floor: {player.floor?.toFixed(1)}</span>
          <span>Ceil: {player.ceiling?.toFixed(1)}</span>
        </div>
      </div>
    );
  };

  return (
    <Card className='border-primary/20 bg-primary/5 mt-[var(--space-2)]'>
      <CardHeader className='pb-[var(--space-1)] pt-[var(--space-3)]'>
        <CardTitle className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
          Start/Sit Comparison ·{' '}
          {data.scoring_format?.replace('_', '-').toUpperCase()} · Week{' '}
          {data.week}
        </CardTitle>
      </CardHeader>
      <CardContent className='pb-[var(--space-3)]'>
        <div className='flex gap-[var(--space-3)]'>
          {renderSide(data.player1, 'Player 1')}
          {renderSide(data.player2, 'Player 2')}
        </div>
      </CardContent>
    </Card>
  );
}

function SearchCard({ data }: { data: SearchResult }) {
  if (!data.found || !data.players?.length) {
    return (
      <Card className='border-muted bg-muted/30 mt-[var(--space-2)]'>
        <CardContent className='p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          {data.message ?? 'No players found.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-muted bg-muted/20 mt-[var(--space-2)]'>
      <CardContent className='p-[var(--space-3)]'>
        <div className='flex flex-wrap gap-[var(--space-2)]'>
          {data.players.map((p) => (
            <div
              key={p.player_id}
              className='flex items-center gap-[var(--space-1)] rounded-md border px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
            >
              <Badge
                variant='outline'
                className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
              >
                {p.position}
              </Badge>
              <span className='font-medium'>{p.player_name}</span>
              <span className='text-muted-foreground'>{p.team}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function SentimentDot({ score }: { score: number | null }) {
  if (score === null) return null;
  const color =
    score > 0.1
      ? 'bg-green-500'
      : score < -0.1
        ? 'bg-red-500'
        : 'bg-yellow-500';
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
      <Card className='border-muted bg-muted/30 mt-[var(--space-2)]'>
        <CardContent className='p-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          {data.message ?? 'No news available.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-muted bg-muted/20 mt-[var(--space-2)]'>
      <CardContent className='divide-y p-0'>
        {data.items.slice(0, 5).map((item, i) => (
          <div key={i} className='px-[var(--space-3)] py-[var(--space-2)]'>
            <div className='flex items-start justify-between gap-[var(--space-2)]'>
              <div className='flex items-start gap-[var(--space-2)] min-w-0'>
                <SentimentDot score={item.sentiment} />
                <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
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
                    className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-green-600 border-green-600'
                  >
                    RTN
                  </Badge>
                )}
              </div>
            </div>
            <div className='mt-0.5 flex items-center gap-[var(--space-2)]'>
              {item.player_name && (
                <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  {item.player_name}
                  {item.team ? ` · ${item.team}` : ''}
                </p>
              )}
              {item.category && (
                <Badge
                  variant='outline'
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] px-[var(--space-1)] py-0 h-[var(--space-4)]'
                >
                  {item.category}
                </Badge>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
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
                className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                onClick={clear}
              >
                <Icons.trash className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                Clear conversation
              </Button>
            </PressScale>
          </div>
        )}

        {/* Message area */}
        <ScrollArea className='flex-1 rounded-lg border'>
          <div className='flex flex-col gap-[var(--gap-stack)] p-[var(--pad-card)]'>
            {messages.length === 0 && (
              <div className='flex flex-col items-center justify-center py-16 text-center'>
                <div className='bg-primary/10 mb-[var(--space-4)] rounded-full p-[var(--space-4)]'>
                  <Icons.sparkles className='text-primary h-[var(--space-8)] w-[var(--space-8)]' />
                </div>
                <h2 className='mb-[var(--space-1)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)] font-semibold'>
                  Your AI Fantasy Advisor
                </h2>
                <p className='text-muted-foreground mb-[var(--space-6)] max-w-sm text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                  Ask me about start/sit decisions, trade analysis, waiver wire
                  pickups, or player projections.
                </p>
                <div className='flex flex-wrap justify-center gap-[var(--space-2)]'>
                  {SUGGESTIONS.map((s) => (
                    <PressScale key={s}>
                      <Button
                        variant='outline'
                        size='sm'
                        className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
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
                    <AvatarFallback className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
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
                                  ? 'bg-primary text-primary-foreground rounded-tr-sm'
                                  : 'bg-muted rounded-tl-sm'
                              }`}
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
                                className='text-muted-foreground flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
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
                                className='text-muted-foreground flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
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
                                className='text-muted-foreground flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
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
                                className='text-muted-foreground flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
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
                  <AvatarFallback className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                    AI
                  </AvatarFallback>
                </Avatar>
                <div className='bg-muted flex items-center gap-[var(--space-1)] rounded-2xl rounded-tl-sm px-[var(--space-4)] py-[var(--space-3)]'>
                  <span className='bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:0ms]' />
                  <span className='bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:150ms]' />
                  <span className='bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:300ms]' />
                </div>
              </div>
            )}

            {/* Error state with retry */}
            {hasError && (
              <div className='flex gap-[var(--space-3)]'>
                <Avatar className='h-[var(--space-8)] w-[var(--space-8)] shrink-0'>
                  <AvatarFallback className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                    AI
                  </AvatarFallback>
                </Avatar>
                <div className='bg-destructive/10 border-destructive/30 flex flex-col gap-[var(--space-2)] rounded-2xl rounded-tl-sm border px-[var(--space-4)] py-[var(--space-3)]'>
                  <p className='text-destructive text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                    Something went wrong. This may be a temporary issue with the AI
                    provider or the data backend.
                  </p>
                  {lastUserMessage && (
                    <PressScale className='self-start'>
                      <Button
                        variant='outline'
                        size='sm'
                        className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
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

        {/* Input form — tap targets ≥ 44px on mobile. */}
        <form onSubmit={handleSubmit} className='flex gap-[var(--space-2)]'>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder='Ask about start/sit, trades, waiver wire...'
            disabled={isLoading}
            className='h-[var(--tap-min)] flex-1 sm:h-9'
          />
          <PressScale>
            <Button
              type='submit'
              disabled={isLoading || !input.trim()}
              className='h-[var(--tap-min)] sm:h-9'
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
      </FadeIn>
    </PageContainer>
  );
}
