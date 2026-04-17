'use client';

import { useChat } from '@ai-sdk/react';
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithToolCalls
} from 'ai';
import { useRef, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Icons } from '@/components/icons';
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

const WIDGET_SUGGESTIONS = [
  'Who should I start at RB?',
  'Compare Mahomes vs Jackson',
  'Any injury news?',
  'Best waiver pickups?'
];

// ---------------------------------------------------------------------------
// Tool result cards (compact versions for widget)
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
      <Card className='border-muted bg-muted/30 mt-1'>
        <CardContent className='p-2 text-xs text-muted-foreground'>
          {data.message ?? 'Player not found.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-primary/20 bg-primary/5 mt-1'>
      <CardHeader className='pb-1 pt-2 px-2'>
        <CardTitle className='flex items-center gap-1 text-xs font-semibold'>
          {data.player_name}
          <Badge variant='outline' className='text-[10px]'>
            {data.position}
          </Badge>
          <span className='text-muted-foreground font-normal'>{data.team}</span>
          <InjuryBadge status={data.injury_status} />
        </CardTitle>
      </CardHeader>
      <CardContent className='pb-2 px-2'>
        <div className='flex gap-3 text-xs'>
          <div>
            <span className='text-muted-foreground'>Proj</span>
            <p className='font-bold text-sm leading-tight'>
              {data.projected_points?.toFixed(1)} pts
            </p>
          </div>
          <div>
            <span className='text-muted-foreground'>Floor</span>
            <p className='font-medium'>{data.projected_floor?.toFixed(1)}</p>
          </div>
          <div>
            <span className='text-muted-foreground'>Ceil</span>
            <p className='font-medium'>{data.projected_ceiling?.toFixed(1)}</p>
          </div>
        </div>
        <p className='text-muted-foreground mt-0.5 text-[10px]'>
          {data.scoring_format?.replace('_', '-').toUpperCase()} · Wk{' '}
          {data.week}, {data.season}
        </p>
      </CardContent>
    </Card>
  );
}

function CompareCard({ data }: { data: CompareResult }) {
  if (!data.found) {
    return (
      <Card className='border-muted bg-muted/30 mt-1'>
        <CardContent className='p-2 text-xs text-muted-foreground'>
          {data.message ?? 'Comparison data not available.'}
        </CardContent>
      </Card>
    );
  }

  const renderSide = (player: PlayerSide | undefined) => {
    if (!player) return null;
    if (player.error) {
      return (
        <div className='flex-1 rounded-md border p-2'>
          <p className='text-xs font-medium'>{player.name}</p>
          <p className='text-muted-foreground text-[10px]'>{player.error}</p>
        </div>
      );
    }
    return (
      <div className='flex-1 rounded-md border p-2'>
        <div className='flex items-center gap-1 mb-0.5'>
          <Badge variant='outline' className='text-[10px]'>
            {player.position}
          </Badge>
          <InjuryBadge status={player.injury_status} />
        </div>
        <p className='text-xs font-semibold'>{player.name}</p>
        <p className='text-lg font-bold'>
          {player.projected_points?.toFixed(1)}{' '}
          <span className='text-[10px] font-normal text-muted-foreground'>
            pts
          </span>
        </p>
        <div className='flex gap-2 text-[10px] text-muted-foreground'>
          <span>Floor: {player.floor?.toFixed(1)}</span>
          <span>Ceil: {player.ceiling?.toFixed(1)}</span>
        </div>
      </div>
    );
  };

  return (
    <Card className='border-primary/20 bg-primary/5 mt-1'>
      <CardHeader className='pb-1 pt-2 px-2'>
        <CardTitle className='text-xs font-semibold'>
          Start/Sit ·{' '}
          {data.scoring_format?.replace('_', '-').toUpperCase()} · Wk{' '}
          {data.week}
        </CardTitle>
      </CardHeader>
      <CardContent className='pb-2 px-2'>
        <div className='flex gap-2'>
          {renderSide(data.player1)}
          {renderSide(data.player2)}
        </div>
      </CardContent>
    </Card>
  );
}

function SearchCard({ data }: { data: SearchResult }) {
  if (!data.found || !data.players?.length) {
    return (
      <Card className='border-muted bg-muted/30 mt-1'>
        <CardContent className='p-2 text-xs text-muted-foreground'>
          {data.message ?? 'No players found.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-muted bg-muted/20 mt-1'>
      <CardContent className='p-2'>
        <div className='flex flex-wrap gap-1'>
          {data.players.map((p) => (
            <div
              key={p.player_id}
              className='flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px]'
            >
              <Badge variant='outline' className='text-[9px]'>
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
  const label =
    score > 0.1 ? 'Positive' : score < -0.1 ? 'Negative' : 'Neutral';
  return (
    <span
      title={`Sentiment: ${label} (${score.toFixed(2)})`}
      className={`inline-block h-2 w-2 rounded-full ${color} shrink-0 mt-1`}
    />
  );
}

function NewsCard({ data }: { data: NewsFeedResult }) {
  if (!data.found || !data.items?.length) {
    return (
      <Card className='border-muted bg-muted/30 mt-1'>
        <CardContent className='p-2 text-xs text-muted-foreground'>
          {data.message ?? 'No news available.'}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className='border-muted bg-muted/20 mt-1'>
      <CardContent className='divide-y p-0'>
        {data.items.slice(0, 3).map((item, i) => (
          <div key={i} className='px-2 py-1.5'>
            <div className='flex items-start gap-1.5'>
              <SentimentDot score={item.sentiment} />
              <p className='text-xs font-medium leading-snug'>
                {item.title ?? item.body_snippet ?? 'Untitled'}
              </p>
            </div>
            {item.player_name && (
              <p className='text-muted-foreground text-[10px] mt-0.5'>
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
// Message renderer (shared between widget parts)
// ---------------------------------------------------------------------------

function MessagePart({
  part,
  partIndex,
  isUser
}: {
  part: { type: string; text?: string; state?: string; output?: unknown };
  partIndex: number;
  isUser: boolean;
}) {
  switch (part.type) {
    case 'text':
      return (
        <div
          key={partIndex}
          className={cn(
            'rounded-2xl px-3 py-1.5 text-xs leading-relaxed whitespace-pre-wrap',
            isUser
              ? 'bg-primary text-primary-foreground rounded-tr-sm'
              : 'bg-muted rounded-tl-sm'
          )}
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
      if (part.state === 'input-streaming' || part.state === 'input-available') {
        return (
          <div
            key={partIndex}
            className='text-muted-foreground flex items-center gap-1 text-[10px]'
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
      if (part.state === 'input-streaming' || part.state === 'input-available') {
        return (
          <div
            key={partIndex}
            className='text-muted-foreground flex items-center gap-1 text-[10px]'
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
      if (part.state === 'input-streaming' || part.state === 'input-available') {
        return (
          <div
            key={partIndex}
            className='text-muted-foreground flex items-center gap-1 text-[10px]'
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
      if (part.state === 'input-streaming' || part.state === 'input-available') {
        return (
          <div
            key={partIndex}
            className='text-muted-foreground flex items-center gap-1 text-[10px]'
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
}

// ---------------------------------------------------------------------------
// Floating Chat Widget
// ---------------------------------------------------------------------------

export function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [lastUserMessage, setLastUserMessage] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const { messages, sendMessage, status, error } = useChat({
    transport: new DefaultChatTransport({ api: '/api/chat' }),
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls
  });

  const isLoading = status === 'streaming' || status === 'submitted';
  const hasError = status === 'error' || !!error;

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (isOpen) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

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
    <>
      {/* Floating action button */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          'fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center',
          'rounded-full bg-gradient-to-br from-primary to-primary/80 text-primary-foreground shadow-lg shadow-primary/25',
          'transition-all duration-200 hover:scale-110 hover:shadow-xl hover:shadow-primary/40',
          'animate-pulse [animation-duration:3s]',
          'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
          isOpen && 'scale-0 opacity-0 pointer-events-none'
        )}
        aria-label='Open AI Advisor chat'
      >
        <Icons.robot className='h-6 w-6' />
        {/* Unread dot when there are messages and widget is closed */}
        {messages.length > 0 && !isOpen && (
          <span className='absolute -top-0.5 -right-0.5 h-3 w-3 rounded-full bg-destructive border-2 border-background' />
        )}
      </button>

      {/* Chat panel */}
      <div
        className={cn(
          'fixed bottom-5 right-5 z-50 flex flex-col',
          'w-[400px] h-[520px] max-h-[calc(100dvh-40px)]',
          'rounded-2xl border bg-background shadow-2xl',
          'transition-all duration-300 ease-out origin-bottom-right',
          isOpen
            ? 'scale-100 opacity-100'
            : 'scale-0 opacity-0 pointer-events-none'
        )}
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-4 py-3 shrink-0'>
          <div className='flex items-center gap-2'>
            <div className='flex h-7 w-7 items-center justify-center rounded-full bg-primary/10'>
              <Icons.robot className='h-4 w-4 text-primary' />
            </div>
            <div>
              <h3 className='text-sm font-semibold leading-none'>AI Advisor</h3>
              <p className='text-[10px] text-muted-foreground mt-0.5'>
                Fantasy football assistant
              </p>
            </div>
          </div>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 w-7 p-0'
            onClick={() => setIsOpen(false)}
            aria-label='Minimize chat'
          >
            <Icons.minus className='h-4 w-4' />
          </Button>
        </div>

        {/* Messages */}
        <ScrollArea className='flex-1 min-h-0'>
          <div className='flex flex-col gap-3 p-3'>
            {messages.length === 0 && (
              <div className='flex flex-col items-center justify-center py-8 text-center'>
                <div className='bg-primary/10 mb-3 rounded-full p-3'>
                  <Icons.robot className='text-primary h-6 w-6' />
                </div>
                <h4 className='mb-0.5 text-sm font-semibold'>
                  AI Fantasy Advisor
                </h4>
                <p className='text-muted-foreground mb-4 max-w-[280px] text-xs'>
                  Ask about start/sit decisions, player projections, or trade
                  analysis.
                </p>
                <div className='flex flex-wrap justify-center gap-1.5'>
                  {WIDGET_SUGGESTIONS.map((s) => (
                    <Button
                      key={s}
                      variant='outline'
                      size='sm'
                      className='text-[10px] h-7 px-2'
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
                  className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}
                >
                  <Avatar className='h-6 w-6 shrink-0'>
                    <AvatarFallback className='text-[10px]'>
                      {isUser ? 'You' : 'AI'}
                    </AvatarFallback>
                  </Avatar>

                  <div
                    className={`flex max-w-[85%] flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}
                  >
                    {message.parts.map((part, partIndex) => (
                      <MessagePart
                        key={partIndex}
                        part={part as { type: string; text?: string; state?: string; output?: unknown }}
                        partIndex={partIndex}
                        isUser={isUser}
                      />
                    ))}
                  </div>
                </div>
              );
            })}

            {/* Typing indicator */}
            {isLoading && (
              <div className='flex gap-2'>
                <Avatar className='h-6 w-6 shrink-0'>
                  <AvatarFallback className='text-[10px]'>AI</AvatarFallback>
                </Avatar>
                <div className='bg-muted flex items-center gap-1 rounded-2xl rounded-tl-sm px-3 py-2'>
                  <span className='bg-muted-foreground h-1 w-1 animate-bounce rounded-full [animation-delay:0ms]' />
                  <span className='bg-muted-foreground h-1 w-1 animate-bounce rounded-full [animation-delay:150ms]' />
                  <span className='bg-muted-foreground h-1 w-1 animate-bounce rounded-full [animation-delay:300ms]' />
                </div>
              </div>
            )}

            {/* Error state */}
            {hasError && (
              <div className='flex gap-2'>
                <Avatar className='h-6 w-6 shrink-0'>
                  <AvatarFallback className='text-[10px]'>AI</AvatarFallback>
                </Avatar>
                <div className='bg-destructive/10 border-destructive/30 flex flex-col gap-1.5 rounded-2xl rounded-tl-sm border px-3 py-2'>
                  <p className='text-destructive text-xs font-medium'>
                    Something went wrong. Please try again.
                  </p>
                  {lastUserMessage && (
                    <Button
                      variant='outline'
                      size='sm'
                      className='self-start text-[10px] h-6'
                      onClick={handleRetry}
                      disabled={isLoading}
                    >
                      Retry
                    </Button>
                  )}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        {/* Input form */}
        <form
          onSubmit={handleSubmit}
          className='flex gap-2 border-t px-3 py-2.5 shrink-0'
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder='Ask about players, matchups...'
            disabled={isLoading}
            className='flex-1 h-8 text-xs'
          />
          <Button
            type='submit'
            disabled={isLoading || !input.trim()}
            size='sm'
            className='h-8 w-8 p-0 shrink-0'
          >
            {isLoading ? (
              <Icons.spinner className='h-3.5 w-3.5 animate-spin' />
            ) : (
              <Icons.send className='h-3.5 w-3.5' />
            )}
          </Button>
        </form>
      </div>
    </>
  );
}
