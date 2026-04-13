'use client';

import { useChat } from '@ai-sdk/react';
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithToolCalls
} from 'ai';
import { useRef, useEffect, useState } from 'react';
import PageContainer from '@/components/layout/page-container';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Icons } from '@/components/icons';

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

interface NewsFeedResult {
  found: boolean;
  message?: string;
  items?: Array<{
    title: string | null;
    source: string;
    published_at: string | null;
    player_name: string | null;
    team: string | null;
    body_snippet: string | null;
    is_ruled_out: boolean;
    is_questionable: boolean;
  }>;
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
      <Card className='border-muted bg-muted/30 mt-2'>
        <CardContent className='p-3 text-sm text-muted-foreground'>
          {data.message ?? 'Player not found.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-primary/20 bg-primary/5 mt-2'>
      <CardHeader className='pb-1 pt-3'>
        <CardTitle className='flex items-center gap-2 text-sm font-semibold'>
          {data.player_name}
          <Badge variant='outline' className='text-xs'>
            {data.position}
          </Badge>
          <span className='text-muted-foreground font-normal'>{data.team}</span>
          <InjuryBadge status={data.injury_status} />
        </CardTitle>
      </CardHeader>
      <CardContent className='pb-3'>
        <div className='flex gap-4 text-sm'>
          <div>
            <span className='text-muted-foreground'>Projected</span>
            <p className='font-bold text-lg leading-tight'>
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
        <p className='text-muted-foreground mt-1 text-xs'>
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
        <div className='flex-1 rounded-lg border p-3'>
          <p className='font-medium'>{player.name}</p>
          <p className='text-muted-foreground text-xs'>{player.error}</p>
        </div>
      );
    }
    return (
      <div className='flex-1 rounded-lg border p-3'>
        <div className='mb-1 flex items-center gap-1'>
          <span className='text-xs text-muted-foreground'>{label}</span>
          <Badge variant='outline' className='text-xs'>
            {player.position}
          </Badge>
          <InjuryBadge status={player.injury_status} />
        </div>
        <p className='font-semibold'>{player.name}</p>
        <p className='text-muted-foreground text-xs'>{player.team}</p>
        <p className='mt-2 text-2xl font-bold'>
          {player.projected_points?.toFixed(1)}{' '}
          <span className='text-sm font-normal text-muted-foreground'>pts</span>
        </p>
        <div className='mt-1 flex gap-3 text-xs text-muted-foreground'>
          <span>Floor: {player.floor?.toFixed(1)}</span>
          <span>Ceil: {player.ceiling?.toFixed(1)}</span>
        </div>
      </div>
    );
  };

  return (
    <Card className='border-primary/20 bg-primary/5 mt-2'>
      <CardHeader className='pb-1 pt-3'>
        <CardTitle className='text-sm font-semibold'>
          Start/Sit Comparison ·{' '}
          {data.scoring_format?.replace('_', '-').toUpperCase()} · Week{' '}
          {data.week}
        </CardTitle>
      </CardHeader>
      <CardContent className='pb-3'>
        <div className='flex gap-3'>
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
      <Card className='border-muted bg-muted/30 mt-2'>
        <CardContent className='p-3 text-sm text-muted-foreground'>
          {data.message ?? 'No players found.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-muted bg-muted/20 mt-2'>
      <CardContent className='p-3'>
        <div className='flex flex-wrap gap-2'>
          {data.players.map((p) => (
            <div
              key={p.player_id}
              className='flex items-center gap-1 rounded-md border px-2 py-1 text-xs'
            >
              <Badge variant='outline' className='text-[10px]'>
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

function NewsCard({ data }: { data: NewsFeedResult }) {
  if (!data.found || !data.items?.length) {
    return (
      <Card className='border-muted bg-muted/30 mt-2'>
        <CardContent className='p-3 text-sm text-muted-foreground'>
          {data.message ?? 'No news available.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-muted bg-muted/20 mt-2'>
      <CardContent className='divide-y p-0'>
        {data.items.slice(0, 5).map((item, i) => (
          <div key={i} className='px-3 py-2'>
            <div className='flex items-start justify-between gap-2'>
              <p className='text-sm font-medium leading-snug'>
                {item.title ?? item.body_snippet ?? 'Untitled'}
              </p>
              <div className='flex shrink-0 gap-1'>
                {item.is_ruled_out && (
                  <Badge variant='destructive' className='text-[10px]'>
                    OUT
                  </Badge>
                )}
                {item.is_questionable && !item.is_ruled_out && (
                  <Badge variant='secondary' className='text-[10px]'>
                    Q
                  </Badge>
                )}
              </div>
            </div>
            {item.player_name && (
              <p className='text-muted-foreground mt-0.5 text-xs'>
                {item.player_name}
                {item.team ? ` · ${item.team}` : ''}
              </p>
            )}
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
  const bottomRef = useRef<HTMLDivElement>(null);

  const { messages, sendMessage, status } = useChat({
    transport: new DefaultChatTransport({ api: '/api/chat' }),
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls
  });

  const isLoading = status === 'streaming' || status === 'submitted';

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;
    sendMessage({ text });
    setInput('');
  }

  function handleSuggestion(text: string) {
    if (isLoading) return;
    sendMessage({ text });
  }

  return (
    <PageContainer
      pageTitle='AI Fantasy Advisor'
      pageDescription='Ask about start/sit decisions, trade analysis, waiver wire pickups, and more'
    >
      <div className='flex h-[calc(100dvh-160px)] flex-col gap-3'>
        {/* Message area */}
        <ScrollArea className='flex-1 rounded-lg border'>
          <div className='flex flex-col gap-4 p-4'>
            {messages.length === 0 && (
              <div className='flex flex-col items-center justify-center py-16 text-center'>
                <div className='bg-primary/10 mb-4 rounded-full p-4'>
                  <Icons.sparkles className='text-primary h-8 w-8' />
                </div>
                <h2 className='mb-1 text-lg font-semibold'>
                  Your AI Fantasy Advisor
                </h2>
                <p className='text-muted-foreground mb-6 max-w-sm text-sm'>
                  Ask me about start/sit decisions, trade analysis, waiver wire
                  pickups, or player projections.
                </p>
                <div className='flex flex-wrap justify-center gap-2'>
                  {SUGGESTIONS.map((s) => (
                    <Button
                      key={s}
                      variant='outline'
                      size='sm'
                      className='text-xs'
                      onClick={() => handleSuggestion(s)}
                    >
                      {s}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => {
              const isUser = message.role === 'user';
              return (
                <div
                  key={message.id}
                  className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
                >
                  <Avatar className='h-8 w-8 shrink-0'>
                    <AvatarFallback className='text-xs'>
                      {isUser ? 'You' : 'AI'}
                    </AvatarFallback>
                  </Avatar>

                  <div
                    className={`flex max-w-[80%] flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}
                  >
                    {message.parts.map((part, partIndex) => {
                      switch (part.type) {
                        case 'text':
                          return (
                            <div
                              key={partIndex}
                              className={`rounded-2xl px-4 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
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
                                className='text-muted-foreground flex items-center gap-2 text-xs'
                              >
                                <Icons.spinner className='h-3 w-3 animate-spin' />
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
                                className='text-muted-foreground flex items-center gap-2 text-xs'
                              >
                                <Icons.spinner className='h-3 w-3 animate-spin' />
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
                                className='text-muted-foreground flex items-center gap-2 text-xs'
                              >
                                <Icons.spinner className='h-3 w-3 animate-spin' />
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
                                className='text-muted-foreground flex items-center gap-2 text-xs'
                              >
                                <Icons.spinner className='h-3 w-3 animate-spin' />
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
              <div className='flex gap-3'>
                <Avatar className='h-8 w-8 shrink-0'>
                  <AvatarFallback className='text-xs'>AI</AvatarFallback>
                </Avatar>
                <div className='bg-muted flex items-center gap-1 rounded-2xl rounded-tl-sm px-4 py-3'>
                  <span className='bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:0ms]' />
                  <span className='bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:150ms]' />
                  <span className='bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:300ms]' />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        {/* Input form */}
        <form onSubmit={handleSubmit} className='flex gap-2'>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder='Ask about start/sit, trades, waiver wire...'
            disabled={isLoading}
            className='flex-1'
          />
          <Button type='submit' disabled={isLoading || !input.trim()}>
            {isLoading ? (
              <Icons.spinner className='h-4 w-4 animate-spin' />
            ) : (
              <Icons.send className='h-4 w-4' />
            )}
            <span className='ml-2'>Send</span>
          </Button>
        </form>
      </div>
    </PageContainer>
  );
}
